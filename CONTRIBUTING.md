# Contributing

Issue、Pull Request、test fixtureには、個人の金融データを含めないでください。銀行返済予定表、
`forecast.json`、PDF、画面キャプチャ、氏名、住所、口座番号、契約番号を添付しないでください。

不具合は `sample-data/` を基にした人工データで再現してください。新しいlender-specific ruleを
追加する場合は、公開可能な公式根拠、または匿名化されたactual validationの方法とverification
statusを示してください。

返済額、利息、残高、金利適用日、端数処理などfinancial correctnessへ影響する変更には、unit test
または人工golden testを追加してください。提出前に次を実行します。

```bash
pytest
python scripts/generate_forecast.py
cd dashboard
npm test
npm run typecheck
npm run lint
npm run build
```

実データでしか再現できない場合は、データ自体を共有せず、公開可能な最小の人工例へ置き換えて
ください。
