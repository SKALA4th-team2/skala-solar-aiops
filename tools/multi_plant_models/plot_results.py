"""Compare per-site improvements against each site's validation-chosen baseline."""
import argparse
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out",default="docs/proposal/evidence/multi_plant_models_20261007")
    args = ap.parse_args()
    out = ROOT/args.out
    df = pd.read_csv(out/"all_metrics.csv")
    kinds = ["LSTM","XGBoost","Prophet","Ensemble","LSTM_Main_Ensemble"]
    plants = df[["plant_id","name","unit"]].drop_duplicates().sort_values(["name","unit"])
    values = df.pivot(index="plant_id",columns="model",values="rmse_improvement_vs_baseline_pct").loc[plants.plant_id,kinds]
    plt.rcParams["font.family"] = "Malgun Gothic"
    plt.rcParams["axes.unicode_minus"] = False
    fig,ax = plt.subplots(figsize=(10,12),layout="constrained")
    im = ax.imshow(values.to_numpy(),cmap="RdBu",vmin=-40,vmax=40,aspect="auto")
    ax.set_xticks(range(5),["LSTM","XGBoost","Prophet","앙상블","LSTM ≥50%\n앙상블"])
    ax.xaxis.tick_top()
    ax.set_yticks(range(len(plants)),[f"{r['name']} {r['unit']}호기" for _,r in plants.iterrows()])
    for row in range(len(plants)):
        for col in range(5):
            value = values.iloc[row,col]
            ax.text(col,row,f"{value:+.1f}%",ha="center",va="center",fontsize=9,
                    color="white" if abs(value)>25 else "#142333")
    ax.set_title("발전소별 시험 RMSE 개선율 · 2025년 365일\n개소별 검증에서 선택한 단순 기준모델 대비 · +값이 개선",pad=45,fontsize=14)
    fig.colorbar(im,ax=ax,shrink=.6,label="RMSE 개선율 (%) · 색 범위 ±40%")
    fig.supxlabel("모델·비중은 이전 검증 구간에서 선택. LSTM 시드 42. 날씨는 ASOS 과거 관측값이며 예보가 아님.",fontsize=9)
    fig.savefig(out/"model_improvement.png",dpi=160)
    plt.close(fig)


if __name__=="__main__":
    main()
