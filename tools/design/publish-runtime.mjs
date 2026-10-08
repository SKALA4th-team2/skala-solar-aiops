/** Publish the reviewed frontend into FastAPI's existing static directory. */
import {copyFile} from 'node:fs/promises';
await import('./build-preview.mjs');
for(const filename of ['index.html','styles.css','app.js','dashboard-core.js','operations.js','server-dashboard.js','hourly-ui.js']){
  await copyFile(new URL('../../docs/design/solar-ops-v01/'+filename,import.meta.url),new URL('../../project/serving_app/static/'+filename,import.meta.url));
}
console.log('Published Solar Ops to FastAPI static directory');
