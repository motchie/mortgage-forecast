# Private data repository

公開repoは `sample-data/` の人工データだけで動作します。実際の住宅ローン入力と銀行実績は、
隣接するprivate repositoryへ分離してください。雛形は
[`examples/private-data-template/`](../examples/private-data-template/) にあります。

データrootの選択優先順位は次のとおりです。

1. `python scripts/generate_forecast.py --data-dir PATH`
2. `MORTGAGE_DATA_DIR`
3. 公開repoの `sample-data/`

指定した外部directoryに不足や形式不正がある場合、sampleへsilent fallbackせずエラー終了します。
directory構成、privacy上の注意、起動方法は雛形READMEを参照してください。初回に集める銀行資料、
入力項目、月次・金利変更・返済額見直し時の更新手順は
[`data-setup-and-updates.md`](data-setup-and-updates.md) にあります。
