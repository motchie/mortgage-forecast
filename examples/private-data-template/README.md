# Mortgage Forecast Private Data

このrepositoryは必ず**非公開（private）**にしてください。公開OSS側には計算コードと
人工sampleだけを置き、個人の金融データはこのrepositoryで管理します。

## 保存してよいもの

計算に必要な匿名化済み数値だけを `data/` に保存します。氏名、住所、口座番号、支店番号、
取引番号などは保存しません。銀行から取得した元PDFや画面キャプチャもcommitしません。
グラフへ年齢を表示する場合はローン設定に生まれ年だけを `borrower_birth_year` として保存し、
氏名や生年月日は保存しません。生まれ年もprivate情報として扱ってください。

`generated/forecast.json` は派生した金融情報を含むためcommitせず、`.gitignore` の対象にします。
private golden testに必要な `private-tests/fixtures/` のsnapshotをcommitする場合は、private
repository内だけに限定し、氏名・住所・口座番号・filesystem pathがないことを確認してください。

```text
mortgage-forecast-private/
  data/
    data-schema.yaml
    loans/
    actual/
    rates/
      actual-rates.yaml
      scenarios.yaml
    sources.yaml
```

公開repoと同じ親directoryへ置く構成を推奨します。

```text
~/src/
  mortgage-forecast/
  mortgage-forecast-private/
```

## 使用方法

macOS / Linux / WSL:

```bash
cd ../mortgage-forecast
export MORTGAGE_DATA_DIR=../mortgage-forecast-private/data
python scripts/dev.py
```

Windows PowerShell:

```powershell
cd ..\mortgage-forecast
$env:MORTGAGE_DATA_DIR="..\mortgage-forecast-private\data"
python scripts/dev.py
```

data YAML / CSVを保存するとforecastが自動再生成され、dashboardも更新されます。

初回に必要な銀行資料、各fieldの意味、月次・金利変更・返済額見直し時の更新手順は、公開repoの
`docs/data-setup-and-updates.md` を参照してください。

実績golden testは次のように実行します。

```bash
MORTGAGE_DATA_DIR=../mortgage-forecast-private/data pytest -m private_actual
```

`data_schema_version` は将来変更される可能性があります。公開repoを更新するときは、対応する
data schema versionとmigration案内を確認してください。

バックアップが必要な場合は、利用者自身が管理し、公開設定を確認したprivate repositoryまたは
暗号化backupを使用してください。特定のGit hosting serviceは必須ではありません。
