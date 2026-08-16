# 初期データと更新手順

この文書は、公開repositoryをcloneし、自分の住宅ローンデータをprivate data directoryへ設定して
ローカル利用する人向けのガイドです。private dataを含むdashboardを認証なしでpublic hostingする
手順ではありません。

## 最初に用意する資料

計算に必要なのは契約・残高・返済・金利の数値です。次の資料から確認します。

- 金銭消費貸借契約書や商品説明書
  - 借入日、当初元金、満期日、返済日、返済方式、返済額見直し、上限ルール
- 銀行画面または最新の返済予定表
  - 基準日、現在残高、現在金利、現在月返済額
- 銀行の返済予定明細
  - 各回の返済日、返済額、元金、利息、返済後残高
- 金利変更通知または金利履歴
  - 新金利と銀行上の適用日
- 利用者自身が置く将来仮定
  - Base / Higher / Stress等の金利pathとsensitivity対象金利

氏名、住所、口座番号、支店番号、顧客番号、契約番号、元PDF、画面キャプチャは不要です。保存する
のは計算に必要な数値と、匿名化した根拠メモだけにしてください。

## 必要なファイル

data rootは次の構成です。ローンが複数ある場合、`loans/` と `actual/` に同じIDのfileを1組ずつ
用意し、`actual-rates.yaml` にも同じIDのentryを追加します。

```text
data/
├─ data-schema.yaml
├─ loans/
│  └─ my-loan.yaml
├─ actual/
│  └─ my-loan.csv
├─ rates/
│  ├─ actual-rates.yaml
│  └─ scenarios.yaml
└─ sources.yaml
```

人工データによる完全な記入例は [`sample-data/`](../sample-data/) にあります。実データfileを
public repository内へ作らず、[`examples/private-data-template/`](../examples/private-data-template/)
を別のprivate directoryへコピーして使用してください。

### `data-schema.yaml`

現在の必須versionです。

```yaml
data_schema_version: "1.0"
dataset_type: private
description: Private local mortgage data
dashboard:
  show_trend_charts: false
```

`dashboard.show_trend_charts` は残高推移・月返済額推移の表示方法です。`true`ならグラフを表示し、
必要に応じてデータ表を開けます。`false`ならグラフを表示せず、年次データ表だけを常時表示します。
省略時は`true`です。一定金利の感応度分析グラフには影響しません。

### `loans/<loan-id>.yaml`

初回にローンごとに入力します。`loan-id` は小文字英数字とhyphenだけを使い、filenameと `id` を
一致させます。`name` も氏名ではなく「Main mortgage」のような匿名labelにします。

| 分類 | 必要な値 | 入手元・注意 |
|---|---|---|
| 契約 | `original_principal`、`disbursement_date`、`maturity_date` | 契約書・返済予定表 |
| 契約者属性 | `borrower_birth_year` | 西暦4桁。グラフと年次表に「その年に迎える年齢」を表示する場合に設定する |
| 返済日 | `payment_day` | 毎月の約定返済日 |
| 現在値 | `current.balance`、`balance_date` | 最新の銀行表示または返済後残高 |
| 現在値 | `current.annual_rate` | `0.0175` は年1.75%を表す |
| 現在値 | `current.monthly_payment` | bonus返済を除く通常月返済額 |
| 利息計算 | `interest_calculation.balance_unit_yen` | 契約で不明なら実績照合で推定し `inferred` にする |
| 見直し | `payment_review.schedule.dates` | 将来の見直し日を明示的に列挙する |
| 金利model | `rate_model.spread` | short prime scenarioを使う場合の貸出金利との差 |

現行engineで検証されている設定は、`repayment.method: equal_payment`、
`bonus_payment: false`、5年ごとの明示的な見直し日、125%上限です。`interval_years` と
`cap_ratio` を変更すれば別商品へ自動対応するわけではありません。見直し日はintervalから自動生成
されないため、`schedule.dates` には現在より後の全日付を記載してください。過去日を残すとdashboard
の「次回見直し」表示も過去日になるため、見直し完了後に削除します。

`borrower_birth_year` は省略可能です。氏名や生年月日は保存せず、生まれ年だけをprivate dataに保存します。
年齢は誕生日現在の満年齢ではなく、`表示年 − borrower_birth_year` で求める「その年に迎える年齢」です。
この値も個人に関する情報のため、実データを公開repositoryへcommitしないでください。

`unpaid_interest_policy` は通常 `error` とし、未払利息がある状態の見直しを未検証仮定で計算する
場合だけ `exclude_unverified` を使用します。

### `actual/<loan-id>.csv`

銀行の返済予定表・実績をgolden truthとして入力します。
以下の数値はformat説明用の人工例です。

```csv
date,payment,principal,interest,balance_after
2027-01-20,70000,50000,20000,9950000
```

- 金額は円単位の整数、日付は `YYYY-MM-DD`
- `payment = principal + interest` を確認
- 前行の `balance_after - 次行のprincipal = 次行のbalance_after` を確認
- 日付順に並べ、同じ返済日を重複させない
- 最初の行の計算前残高は `balance_after + principal` として復元される
- 最初の行が `current.balance_date` の次回返済なら、その復元残高を
  `current.balance` と一致させる

構造上CSV fileは必須です。少なくとも1行の銀行値を入れるとgolden validationが有効になります。
銀行値を取得できない場合は推測値で埋めず、検証未完了として扱ってください。

### `rates/actual-rates.yaml`

golden CSVの各返済に使われた実金利をローンIDごとに記録します。

```yaml
my-loan:
  application_rule: next_payment_after_effective_date
  verification_status: actual
  changes:
    - effective_date: 2026-01-21
      annual_rate: "0.0180"
```

現在の計算境界は、`effective_date` より**後**の最初の返済から新金利を使うstrict comparisonです。
最初のgolden CSV返済日より前に、少なくとも1件のrateを置いてください。銀行の「適用日」の意味が
異なる場合は、境界前後の返済予定表で確認し、無理に一致させず `unverified` としてください。

### `rates/scenarios.yaml`

これは銀行実績ではなく、利用者が置く将来仮定です。

- `current`: 現在の貸出金利が続く機械的case
- `base` / `higher` / `stress`: 任意の貸出金利path
- `short_prime_path`: short primeとloan側spreadから貸出金利を導くcase
- `settings.sensitivity_rates`: 一定金利比較で表示する年率一覧
- `updated_at`: 仮定を最後に見直した日
- `stale_after_days`: scenarioが古いと警告するまでの日数

年率は小数で記述します。たとえば2.5%は `"0.0250"` です。scenarioは将来予測ではなく仮定なので、
`verification_status: scenario` とします。Current / Base / Higher / Stressを用意するとdashboardの
標準比較が分かりやすくなります。

### `sources.yaml`

数値やルールの根拠を匿名化して記録します。最低1件を `type: actual` とし、返済予定表の取得日を
残します。契約ルールは `contractual` または `official_product_rule`、実績からの推定は
`inferred`、未確認事項は `unverified` とします。

loan YAMLの `interest_calculation.source_id` と `payment_review.schedule.source_id` に書いたIDは、
`sources` 内にも同じIDで用意します。また、engineがwarningの根拠として使う
`loan-rate-spread-inferred`、`payment-cap-rounding-unverified`、
`unpaid-interest-review-unverified`、`final-payment-rounding-unverified` は、人工sampleのentryを
雛形として残してください。実績根拠がないものを `contractual` へ変更してはいけません。

銀行の公開商品page以外のprivate URL、local filesystem path、氏名や契約番号は書かないでください。

## 初回セットアップ手順

1. 公開repoと同じ親directoryにprivate data directoryを作る。
2. private templateの構成をコピーし、上記5種類のfileを作る。
3. まずloan YAMLの契約値と現在値を入力する。
4. actual CSVとactual ratesを同じ返済期間について入力する。
5. scenarioとsensitivityを人工sampleから独立した自分の仮定として入力する。
6. sourcesへ根拠とverification statusを記録する。
7. 次の1コマンドで検証・生成・dashboard起動を行う。

```bash
python scripts/dev.py --data-dir ../mortgage-forecast-private/data
```

起動後に確認する項目:

- `Dashboard data: external` と表示される
- Model Statusのgolden testがPASSしている
- maximum errorが許容範囲内で、0円でない場合は理由が説明できる
- 現在残高・月返済額・ローン本数が銀行画面と一致する
- Current / Base / Higher / Stressとsensitivityのloan別・combined結果がある
- warningの `inferred` / `unverified` を読み、契約上の事実と混同していない

銀行実績testを持つ場合は、別terminalで次も実行します。

```bash
MORTGAGE_DATA_DIR=../mortgage-forecast-private/data pytest -m private_actual
```

## 更新時に必要なデータ

### 毎月または銀行画面を確認したとき

必要なのは最新の返済後残高、残高基準日、適用金利、月返済額、返済明細です。

1. `loans/<id>.yaml` の `current.balance`、`balance_date`、`annual_rate`、
   `monthly_payment` を最新表示へ更新する。
2. 銀行値を取得できた場合、`actual/<id>.csv` に返済日・返済額・元金・利息・返済後残高を追加する。
3. 起動中なら保存するだけで自動再生成される。停止中なら `python scripts/dev.py ...` を実行する。
4. Model Statusと最新行の誤差を確認する。

### 金利変更通知を受けたとき

1. `current.annual_rate` と、その金利が現在値になった基準日を銀行表示に合わせる。
2. `actual-rates.yaml` の `changes` にeffective dateと新年率を追加する。
3. 金利変更境界の前後にある銀行返済明細をactual CSVへ追加する。
4. 0円一致しない場合は、適用境界、日割り、付利残高単位、端数処理を確認する。

### 返済額見直しが行われたとき

1. `current.monthly_payment` を新しい返済額へ更新する。
2. 完了した日を `payment_review.schedule.dates` から除き、次回以降の日付を追加する。
3. 見直し前後の返済明細をactual CSVへ追加し、125%上限と端数処理を確認する。
4. 未払利息がある場合は、警告を確認し、銀行仕様が不明なら `unverified` のままにする。

### 将来の見方を変えたいとき

`scenarios.yaml` のrate path、`terminal_rate`、`sensitivity_rates`、`updated_at` だけを更新します。
実際に銀行から通知された金利と、利用者が仮定したscenarioを同じ項目へ混在させないでください。

## 更新しなくてよいもの

- `forecast.json`: generatorが作るため手編集しない
- `original_principal`、`disbursement_date`、`borrower_birth_year`: 契約者変更がない限り固定
- 過去のactual CSV行: 銀行値の訂正がない限り上書きしない
- 元PDFや画面キャプチャ: repositoryへ保存しない

データ更新前にprivate directoryをbackupし、更新後はgit diff等で意図した数値だけが変わったことを
確認してください。public issueやPull Requestへ実データを貼らないでください。
