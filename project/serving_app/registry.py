"""Native MLflow tracking and atomic deployment of immutable model/scaler bundles."""
import importlib.metadata
import shutil
import uuid
from serving_app import runtime as rt

def client():
    import mlflow
    mlflow.set_tracking_uri('sqlite:///'+(rt.root()/'mlflow.db').as_posix())
    return mlflow.MlflowClient()

def register(model,scaler_path,metadata,example,*,gate,kind):
    import mlflow
    import mlflow.tensorflow
    from mlflow.models import infer_signature
    import numpy as np
    c=client();name='solar-backend';experiment=c.get_experiment_by_name(name)
    eid=experiment.experiment_id if experiment else c.create_experiment(name,artifact_location=(rt.root()/'mlartifacts').as_uri())
    pid=metadata['plant_id'];pending=rt.plant_dir(pid)/'pending'/uuid.uuid4().hex;pending.mkdir(parents=True)
    model.save(pending/'model.keras');shutil.copy2(scaler_path,pending/'scaler.pkl');rt.write(pending/'metadata.json',metadata)
    with mlflow.start_run(experiment_id=eid,run_name=f'{pid}-{kind}') as run:
        mlflow.set_tags({'plant_id':pid,'kind':kind,'contract':rt.CONTRACT,'gate_passed':str(gate['passed']),
                         'train_end':metadata['train_end'],'publication_cutoff_verified':'false'})
        for key in ['rmse_kwh','limit_kwh']:
            if gate.get(key) is not None:mlflow.log_metric(key,gate[key])
        mlflow.log_dict(gate,'gate.json');mlflow.log_dict(metadata,'metadata.json')
        if not gate['passed']:return dict(promoted=False,gate=gate,run_id=run.info.run_id,reason='gate_failed')
        expected=model(example,training=False).numpy()
        logged=mlflow.tensorflow.log_model(model,name='model',signature=infer_signature(example,expected),
             input_example=example,extra_files=[str(pending/'scaler.pkl'),str(pending/'metadata.json')],
             pip_requirements=[f'{p}=={importlib.metadata.version(p)}' for p in ['tensorflow','keras','numpy','cloudpickle']])
        registered=mlflow.register_model(logged.model_uri,rt.model_name(pid));version=str(registered.version)
        reloaded=mlflow.tensorflow.load_model(f'models:/{rt.model_name(pid)}/{version}')
        np.testing.assert_allclose(reloaded(example,training=False).numpy(),expected,rtol=1e-5,atol=1e-5)
        destination=rt.version_dir(pid,version);destination.parent.mkdir(parents=True,exist_ok=True)
        manifest=dict(metadata,contract=rt.CONTRACT,version=version,model_name=rt.model_name(pid),run_id=run.info.run_id,
                      gate=gate,created_at=rt.now(),hashes={f:rt.sha(pending/f) for f in ['model.keras','scaler.pkl']})
        rt.write(pending/'manifest.json',manifest);pending.rename(destination)
        c.set_model_version_tag(rt.model_name(pid),version,'scaler_sha256',manifest['hashes']['scaler.pkl'])
        return dict(promoted=False,version=version,gate=gate,run_id=run.info.run_id)

def archive_bundle(plant_id, version):
    from serving_app import model_store
    receipt = model_store.publish(plant_id, str(version))
    if receipt:
        c = client()
        for key, value in receipt.items():
            c.set_model_version_tag(rt.model_name(plant_id), str(version), 'archive_' + key, value)
    return receipt


def activate(plant_id,version,*,expected_version=None,reason='gate_passed'):
    """Caller holds worker lock. Load first; restore registry on pointer write failure."""
    from serving_app.model_loader import load_bundle
    candidate=load_bundle(plant_id,str(version))
    if not candidate.manifest['gate']['passed']:raise ValueError('Cannot promote rejected model')
    try:previous=rt.current(plant_id)
    except FileNotFoundError:previous=None
    if expected_version is not None and (previous is None or str(previous['version'])!=str(expected_version)):
        raise ValueError('Current version changed during training')
    # New deployments require verified storage; rollback only loads an approved bundle.
    if reason != 'manual_rollback':
        archive_bundle(plant_id, version)
    c=client();name=rt.model_name(plant_id)
    pointer=dict(version=str(version),previous_version=previous['version'] if previous else None,updated_at=rt.now(),reason=reason)
    try:
        c.transition_model_version_stage(name,str(version),'Production',archive_existing_versions=True)
        c.set_registered_model_alias(name,'champion',str(version))
        rt.write(rt.plant_dir(plant_id)/'current.json',pointer)
    except Exception:
        c.transition_model_version_stage(name,str(version),'Archived')
        if previous:
            c.transition_model_version_stage(name,str(previous['version']),'Production',archive_existing_versions=True)
            c.set_registered_model_alias(name,'champion',str(previous['version']))
        raise
    rt.event(plant_id,'production_changed',pointer)
    return pointer

def reconcile():
    """Recover a crash between registry promotion and atomic local pointer write."""
    c=client()
    for pid in rt.catalog()['plants']:
        try:pointer=rt.current(pid)
        except FileNotFoundError:continue
        name=rt.model_name(pid);version=str(pointer['version'])
        versions=c.search_model_versions(f"name='{name}'")
        production=[str(v.version) for v in versions if v.current_stage=='Production']
        if production!=[version]:c.transition_model_version_stage(name,version,'Production',archive_existing_versions=True)
        try:alias=str(c.get_model_version_by_alias(name,'champion').version)
        except Exception:alias=None
        if alias!=version:c.set_registered_model_alias(name,'champion',version)

def rollback(plant_id,version):
    with rt.lock():
        old=rt.current(plant_id)
        if str(old['version'])==str(version):return old
        return activate(plant_id,version,expected_version=old['version'],reason='manual_rollback')
