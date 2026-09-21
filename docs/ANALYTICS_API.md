# 顧客利用状況分析 API (Analytics API)

ASTEMPO 売上台帳ログから取り込んだ `intake_items` データを、社内別システムから安全に参照するための読み取り専用 REST API。

---

## 1. 概要

| 項目 | 内容 |
|---|---|
| 用途 | 顧客利用状況分析（来店履歴、購買傾向、商品分類別集計 など） |
| ベース URL | `https://factory.kingdrysystem.com/fi/api/v1/analytics` |
| プロトコル | **HTTPS 必須**（HTTP は 400） |
| メソッド | GET のみ（書き込み・更新 API は一切提供しない） |
| 利用形式 | JSON |
| 文字コード | UTF-8 |
| 認証 | `Authorization: Bearer <API_KEY>` ヘッダ |
| 利用元 | **`https://kingdrysystem.com`** からのみ許可 |
| バージョン | v1 |

---

## 2. セキュリティ仕様

API は次の 4 層で防御している。**いずれか 1 つでも失敗すれば即座にリクエストを拒否し、監査ログに記録する**。

### 2.1 HTTPS 必須

nginx が `X-Forwarded-Proto: https` を付与しない限り受け付けない。HTTP 平文アクセスは `400 https_required` で拒否。

### 2.2 Origin / Referer ホワイトリスト

- 許可ホスト: **`kingdrysystem.com`** （スキームは https のみ）
- ブラウザからの呼び出しは `Origin` ヘッダ、サーバ間呼び出しは `Referer` ヘッダで判定
- どちらも欠落・不一致なら `403 forbidden_origin`
- 環境変数 `ANALYTICS_API_EXTRA_ORIGINS`（カンマ区切り）で追加ホストを許可可能

### 2.3 API キー認証 (Bearer Token)

- ヘッダ: `Authorization: Bearer <API_KEY>`
- サーバ側は環境変数 `ANALYTICS_API_KEY` と **定数時間比較**（タイミング攻撃対策）
- 不一致または欠落で `401 unauthorized`
- キーは推測困難な乱数を 32 バイト以上で生成すること:

  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(48))"
  ```

### 2.4 レート制限（スライディングウィンドウ 60 秒）

| 対象 | 既定値 | 環境変数 |
|---|---|---|
| 1 IP あたり | 60 req/min | `ANALYTICS_API_RATE_IP` |
| 1 API キーあたり | 300 req/min | `ANALYTICS_API_RATE_KEY` |

超過時は `429 rate_limited` + `Retry-After` ヘッダ。

> 注: プロセス内インメモリ実装のため、gunicorn ワーカー間では合算されない。複数ワーカー構成で厳密制御が必要な場合は Redis ベースの実装に切り替えること。

### 2.5 その他

- ページネーション上限 `limit=1000`（DoS 防止）
- `customer_name`・`q` などの入力は長さ制限あり（最大 100 文字）
- SQL は **すべて SQLAlchemy ORM 経由**（SQL インジェクション無効化）
- レスポンスにはエラー詳細を返さない（情報漏洩防止）
- すべてのアクセスを `log/analytics_api_audit.log` に TSV で記録（14 ファイルローテーション）

### 2.6 CORS

許可オリジン一致時のみ次のヘッダを付与:

```
Access-Control-Allow-Origin: https://kingdrysystem.com
Vary: Origin
Access-Control-Allow-Methods: GET, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Max-Age: 600
```

`Allow-Credentials` は **付与しない**（Cookie 共有によるセッション混入を防止）。

---

## 3. 認証ヘッダ

すべてのリクエストに以下を付与:

```http
Authorization: Bearer <ANALYTICS_API_KEY>
Origin: https://kingdrysystem.com
```

サーバ間呼び出しで `Origin` を付けない場合は `Referer: https://kingdrysystem.com/...` を付ければ可。

### サンプル (curl)

```bash
curl -sS \
  -H "Authorization: Bearer $ANALYTICS_API_KEY" \
  -H "Origin: https://kingdrysystem.com" \
  "https://factory.kingdrysystem.com/fi/api/v1/analytics/health"
```

### サンプル (Python / requests)

```python
import os
import requests

BASE = 'https://factory.kingdrysystem.com/fi/api/v1/analytics'
HEADERS = {
    'Authorization': f"Bearer {os.environ['ANALYTICS_API_KEY']}",
    'Origin': 'https://kingdrysystem.com',
}

r = requests.get(f'{BASE}/customers/summary',
                 params={'customer_name': '山田 太郎',
                         'from_date': '2026-01-01',
                         'to_date': '2026-05-25'},
                 headers=HEADERS, timeout=10)
r.raise_for_status()
print(r.json())
```

### サンプル (JavaScript / fetch、ブラウザ)

```javascript
// https://kingdrysystem.com/ 上で動作する想定
const res = await fetch(
  'https://factory.kingdrysystem.com/fi/api/v1/analytics/customers/search?q=' +
    encodeURIComponent('山田'),
  {
    headers: {
      'Authorization': `Bearer ${API_KEY}`,
      // Origin は fetch が自動付与
    },
    // credentials は省略 (Cookie 共有しない)
  }
);
const data = await res.json();
```

---

## 4. エンドポイント一覧

| # | メソッド | パス | 説明 |
|---|---|---|---|
| 1 | GET | `/health` | 接続確認 |
| 2 | GET | `/stores` | 店舗マスタ一覧 |
| 3 | GET | `/intake-items` | 入荷品一覧（汎用フィルタ） |
| 4 | GET | `/customers/search` | 顧客名で部分一致検索＋集計 |
| 5 | GET | `/customers/summary` | 指定顧客のサマリ統計 |
| 6 | GET | `/customers/history` | 指定顧客の利用明細 |
| 7 | GET | `/stats/daily` | 日次集計（件数・売上・ユニーク顧客数） |
| 8 | GET | `/stats/products` | 商品名別集計 |

---

## 5. 各エンドポイント詳細

### 5.1 `GET /health`

接続確認。DB SELECT 1 を実行。

**レスポンス**
```json
{ "status": "ok", "time": "2026-05-25T04:14:38.476587Z" }
```

---

### 5.2 `GET /stores`

`stores.is_active = true` の店舗一覧。

**レスポンス**
```json
{
  "count": 15,
  "items": [
    { "store_code": "0002", "store_name": "オザム日の出店" },
    { "store_code": "0006", "store_name": "栄町店" }
  ]
}
```

---

### 5.3 `GET /intake-items`

入荷品の一覧。フィルタ＋ページネーション。

**クエリパラメータ**

| 名前 | 型 | 必須 | 説明 |
|---|---|---|---|
| `from_date` | date | × | 預り日の下限 (YYYY-MM-DD / YYYY/MM/DD / YYYYMMDD) |
| `to_date` | date | × | 預り日の上限 |
| `store_code` | string | × | 店舗コード (例: `0002`) |
| `intake_status` | string | × | 入荷区分 (`通常` / `工場請求中` / `完了済` 等) |
| `customer_name` | string | × | 顧客名（完全一致） |
| `limit` | int | × | 1〜1000 (既定 100) |
| `offset` | int | × | 既定 0 |

**レスポンス**
```json
{
  "total": 1234,
  "limit": 100,
  "offset": 0,
  "items": [
    {
      "id": 5678,
      "store_code": "0002",
      "store_name": "オザム日の出店",
      "slip_number": "039510",
      "tag_number": "00-898",
      "product_name": "Ｙシャツ",
      "customer_name": "山田 太郎",
      "amount": 133,
      "quantity": 1,
      "intake_date": "2025-11-28",
      "scheduled_date": "2025-11-28",
      "intake_status": "通常",
      "status_code": "returned_to_customer",
      "status_name": "返却済",
      "shipped_at": null,
      "returned_at": "2025-12-06T17:32:00+09:00",
      "wrapping": null,
      "shipping_method": null,
      "imported_at": "2025-11-28T09:17:00+09:00"
    }
  ]
}
```

> **2026-09-21 変更**: `returned_at`（返却日時）を追加し、お客様に返却した品目は
> `status_code: "returned_to_customer"` / `status_name: "返却済"` を返すようにした。
> それまでは返却した品物も `入荷` のままだった。既存の項目の意味と型は変えていない。

> **2026-09-21 変更（2）**: 店舗が工場へ遅れ品を請求した品目は `requested` / `請求中` を返すようにした。
> 請求が出荷済になった品目は `shipped` / `出荷済` になり、`shipped_at` に出荷の時刻が入る。
> 工場システム（king-req）の請求と `intake_items` を突き合わせて反映している。
> 2025-10-01 以降の過去の請求も反映済み（請求中 63 件、`入荷` → `出荷済` 506 件。返却済の品目は表示が変わらない）。

**品目の状態 (`status_code` / `status_name`)**

| `status_code` | `status_name` | 意味 |
|---|---|---|
| `received` | 入荷 | 店舗で受け付けた（取り込み時の初期状態） |
| `requested` | 請求中 | 店舗が工場へ遅れ品として請求している（工場の請求一覧で 請求受・確認済） |
| `shipped` | 出荷済 | 工場から店舗へ出荷した（工場のスキャン、または店舗の請求を出荷済にした） |
| `returned` | 再戻 | 店舗から工場へ戻した（仕上げ直し等）。**お客様への返却ではない** |
| `trouble_in_progress` | トラブル対応中 | |
| `trouble_resolved` | トラブル対応済 | |
| `rewashing` | 再洗中 | |
| `returned_to_customer` | 返却済 | **お客様に返却した**。`returned_at` が入っている品目 |

- `returned_at` が入っている品目は、工場側の状態（入荷・出荷済など）に関係なく `returned_to_customer` / `返却済` を返す。多くの品物は工場の出荷スキャンを経ずに、`入荷` から直接 `返却済` になる。
- `returned_at` が `null` の品目は、従来どおり工場側の状態を返す。
- 請求中・出荷済は、店舗の請求の状態が変わるたびに変わる（出荷済を取り消すと請求中に戻る）。請求の登録・出荷の操作の直後に反映し、取りこぼしは毎時 20 分に補正する。請求したときに入荷データがまだ無い品物（当日受付分）は、取り込まれた後の補正で請求中になる。
- `returned_at` は返却日時（JST、`+09:00` 付き ISO 8601、分単位）。半蔵の売上台帳を返却日で検索した CSV（`uriage_daityo_henkyakubi_shitei<YYYY-MM-DD>.csv`）の「返却日時」列の値。
  - 毎朝 05:00 に、前日までの直近 7 日分を取り込む。前日の返却は翌朝 05:00 以降に反映される。
  - 同じ品物が 2 回返却されたときは、新しい返却日時になる。
  - 取消列が `-` 以外の行は返却済にしない。
  - タグが空の行（会員登録料・ﾏﾃﾞ 早期引取です 等）は、店舗・伝票No・預り日・商品名が一致する行を返却済にする。返却のときに追記されたメモ行（LINE使用の記録 等）は `intake_items` に無いので現れない。
  - 過去分は 2025-10-01（`intake_items` の最古の預り日）以降の返却を反映済み。

---

### 5.4 `GET /customers/search`

顧客名（部分一致）で検索し、来店回数・品目数・売上合計・初回/最終来店日を返す。
結果は最終来店日の新しい順（同日の場合は顧客名順）。

**クエリパラメータ**

| 名前 | 型 | 必須 | 説明 |
|---|---|---|---|
| `q` | string | ✓ | 検索文字列（1〜100 文字、部分一致）。`%` と `_` はワイルドカードではなく文字として扱う |
| `from_date` | date | × | 集計期間下限 |
| `to_date` | date | × | 集計期間上限 |
| `store_code` | string | × | 店舗フィルタ |
| `limit` | int | × | 1〜1000 (既定 100) |
| `offset` | int | × | 既定 0 |

**レスポンス**
```json
{
  "query": "山田",
  "total": 3,
  "limit": 100,
  "offset": 0,
  "items": [
    {
      "customer_name": "山田 太郎",
      "visit_count": 42,
      "item_count": 97,
      "total_amount": 38450,
      "first_intake_date": "2024-04-10",
      "last_intake_date": "2026-05-15"
    }
  ]
}
```

| フィールド | 定義 |
|---|---|
| `total` | ヒットした顧客名の数（`items` の総件数） |
| `visit_count` | 来店回数。定義は [5.5 の表](#回数フィールドの定義) と同じ |
| `item_count` | 品目数（明細行数） |

> 顧客名は DB の照合順序でグループ化される（全角/半角スペースの違いなどは同一視。§10 参照）。
> 同一視された表記のうちどれが `customer_name` として返るかは不定。

---

### 5.5 `GET /customers/summary`

指定顧客の利用統計（集計）を返す。

**クエリパラメータ**

| 名前 | 型 | 必須 | 説明 |
|---|---|---|---|
| `customer_name` | string | ✓ | 顧客名（完全一致） |
| `from_date` | date | × | 集計期間下限 |
| `to_date` | date | × | 集計期間上限 |
| `store_code` | string | × | 店舗フィルタ |

**レスポンス**
```json
{
  "customer_name": "山田 太郎",
  "visit_count": 42,
  "slip_count": 45,
  "item_count": 97,
  "total_amount": 38450,
  "total_quantity": 97,
  "first_intake_date": "2024-04-10",
  "last_intake_date": "2026-05-15",
  "avg_interval_days": 18.66,
  "top_stores": [
    { "store_code": "0002", "store_name": "オザム日の出店",
      "visit_count": 38, "item_count": 90, "total_amount": 34200 }
  ],
  "top_products": [
    { "product_name": "Ｙシャツ", "count": 30 },
    { "product_name": "スーツ上下", "count": 8 }
  ]
}
```

#### 回数フィールドの定義

| フィールド | 定義 |
|---|---|
| `visit_count` | **来店回数** = （店舗, 預り日）のユニーク数。同じ店舗に同じ日に出した分は、何品目・何伝票でも 1 回 |
| `slip_count` | **伝票数** = （店舗, 預り日, 伝票No）のユニーク数。伝票No の無い旧データ（全体の約 1%）は、同じ店舗・同じ預り日の分を 1 伝票とみなす |
| `item_count` | **品目数** = 明細行数。`/customers/history` の `total` と一致 |
| `avg_interval_days` | **平均来店間隔** =（最終預り日 − 初回預り日）÷（ユニークな預り日の数 − 1）。小数 2 桁。来店日が 1 日以下なら `null` |
| `top_stores[]` | 来店回数の多い順に最大 5 店舗。`visit_count` はその店舗でのユニークな預り日の数 |
| `top_products[].count` | その商品の品目数（多い順に最大 5 件） |

> **2026-09-20 変更**: それまで `visit_count`（`top_stores[].visit_count`、`/customers/search` の `visit_count` も同様）は
> 品目数を返しており、`avg_interval_days` も品目数で割っていた。上表の定義に修正し、従来の値は `item_count` として残した。

---

### 5.6 `GET /customers/history`

指定顧客の利用明細を新しい順に返す。

**クエリパラメータ**

| 名前 | 型 | 必須 | 説明 |
|---|---|---|---|
| `customer_name` | string | ✓ | 顧客名（完全一致） |
| `from_date` / `to_date` | date | × | 預り日範囲 |
| `store_code` | string | × | 店舗フィルタ |
| `limit` / `offset` | int | × | ページネーション |

**レスポンス**: `intake-items` と同形式（`status_code` / `status_name` / `returned_at` の意味も同じ）。

---

### 5.7 `GET /stats/daily`

日別の入荷件数・売上合計・ユニーク顧客数。

**クエリパラメータ**

| 名前 | 型 | 必須 | 説明 |
|---|---|---|---|
| `from_date` | date | ✓ | 期間下限 |
| `to_date` | date | ✓ | 期間上限（最大 366 日） |
| `store_code` | string | × | 店舗フィルタ |

**レスポンス**
```json
{
  "from_date": "2026-01-01",
  "to_date": "2026-05-25",
  "store_code": null,
  "series": [
    { "date": "2026-01-04", "item_count": 230,
      "total_amount": 42100, "unique_customers": 89 }
  ]
}
```

---

### 5.8 `GET /stats/products`

商品名別の取扱件数・売上合計・ユニーク顧客数を上位 N 件で返す。

**クエリパラメータ**

| 名前 | 型 | 必須 | 説明 |
|---|---|---|---|
| `from_date` / `to_date` | date | × | 集計期間 |
| `store_code` | string | × | 店舗フィルタ |
| `limit` | int | × | 1〜500 (既定 50) |

**レスポンス**
```json
{
  "limit": 50,
  "items": [
    { "product_name": "Ｙシャツ", "item_count": 12500,
      "total_amount": 1662500, "unique_customers": 980 }
  ]
}
```

---

## 6. ステータスコード一覧

| HTTP | error 値 | 意味 | 対応 |
|---|---|---|---|
| 200 | — | 成功 | — |
| 400 | `https_required` | HTTPS 必須 | https で呼ぶ |
| 400 | `invalid date format: <val>` | 日付形式不正 | YYYY-MM-DD で送る |
| 400 | `<param> is required` | 必須パラメータ欠落 | パラメータを付与 |
| 400 | `<param> too long` | 入力長超過（100 文字） | 短くする |
| 400 | `to_date must be >= from_date` | 期間が逆転 | 範囲を見直す |
| 400 | `date range too wide (max 366 days)` | 366 日超 | 範囲を狭める |
| 401 | `unauthorized` | API キー不正 or 欠落 | Bearer トークン確認 |
| 403 | `forbidden_origin` | Origin/Referer 不一致 | `kingdrysystem.com` から呼ぶ |
| 429 | `rate_limited` | レート超過 | `Retry-After` 秒後に再試行 |
| 503 | `server_misconfigured` | サーバ側で API キー未設定 | 運用担当に連絡 |
| 503 | `db_unavailable` | DB 接続失敗 | しばらく待って再試行 |

---

## 7. 監査ログ

すべての受理・拒否を `log/analytics_api_audit.log` に TSV 形式で記録（10MB ローテーション、14 世代保持）。

```
2026-05-25T13:14:38+0900    accept    ip=10.0.0.5    path=/fi/api/v1/analytics/customers/summary    method=GET    key=ab12cd34ef56
2026-05-25T13:14:39+0900    reject_origin    ip=203.0.113.7    path=/fi/api/v1/analytics/health    reason=origin_mismatch    origin=https://evil.example.com    referer=
```

利用者識別は API キーの SHA-256 先頭 12 桁（生キーは記録しない）。

---

## 8. 運用手順

### 8.1 API キーの発行

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

生成した値を `.env` の `ANALYTICS_API_KEY=...` に設定。利用側システムにも同じ値を共有（環境変数として）。

### 8.2 環境変数（factory-intake-shipping `.env`）

```ini
# 必須
ANALYTICS_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# 任意（既定値あり）
ANALYTICS_API_RATE_IP=60
ANALYTICS_API_RATE_KEY=300
ANALYTICS_API_EXTRA_ORIGINS=  # 追加許可オリジン (カンマ区切り、通常空欄)
```

### 8.3 サービス再起動

```bash
sudo systemctl restart factory-shipping
```

### 8.4 nginx 設定（参考）

`factory.kingdrysystem.com` の HTTPS ブロックで `/fi/api/v1/analytics/` を factory-shipping にプロキシ。`/fi/` 全体をプロキシしている既存設定でそのまま動作する。

```nginx
location /fi/ {
    proxy_pass http://unix:/var/www/html/factory-intake-shipping/gunicorn.sock;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Origin $http_origin;
    proxy_set_header Referer $http_referer;
}
```

### 8.5 キーローテーション

1. 新キー生成
2. `.env` の `ANALYTICS_API_KEY` を新値に更新
3. `sudo systemctl restart factory-shipping`
4. 利用側システムにも新キーを反映
5. 旧キーを使った 401 が監査ログに残らないこと確認

> 一時的に旧キーも受け付けたい場合は、コードを `ANALYTICS_API_KEYS`（カンマ区切り）対応に拡張すること。現状は単一キー。

---

## 9. テスト用 curl 一括サンプル

```bash
export BASE='https://factory.kingdrysystem.com/fi/api/v1/analytics'
export HDR_AUTH="Authorization: Bearer $ANALYTICS_API_KEY"
export HDR_ORIGIN="Origin: https://kingdrysystem.com"

# ヘルスチェック
curl -sS -H "$HDR_AUTH" -H "$HDR_ORIGIN" "$BASE/health" | jq .

# 店舗マスタ
curl -sS -H "$HDR_AUTH" -H "$HDR_ORIGIN" "$BASE/stores" | jq .

# 顧客検索
curl -sS -H "$HDR_AUTH" -H "$HDR_ORIGIN" \
  "$BASE/customers/search?q=%E5%B1%B1%E7%94%B0" | jq .

# 顧客サマリ
curl -sS -H "$HDR_AUTH" -H "$HDR_ORIGIN" \
  "$BASE/customers/summary?customer_name=%E5%B1%B1%E7%94%B0+%E5%A4%AA%E9%83%8E" | jq .

# 日次サマリ
curl -sS -H "$HDR_AUTH" -H "$HDR_ORIGIN" \
  "$BASE/stats/daily?from_date=2026-01-01&to_date=2026-05-25" | jq .

# 商品別 TOP
curl -sS -H "$HDR_AUTH" -H "$HDR_ORIGIN" \
  "$BASE/stats/products?from_date=2026-04-01&to_date=2026-04-30&limit=20" | jq .
```

---

## 10. 既知の制限事項

- **`intake_date`（預り日）の定義**: 半蔵（ASTEMPO）の売上台帳ログの `預り日` 列そのもの。店舗で受付した日であり、工場への入荷日でも取り込み実行日でもない。売上台帳ログを「預り日 = 当日」の条件で毎晩 22:30 に出力し、22:35 に取り込むため、通常は `imported_at` の日付と一致する（後日の再取得分は一致しない）。
- **取消伝票は含まれない**: 売上台帳ログは「取消表示＝非表示」で出力している。店舗で取消された伝票は API に存在せず、伝票No が欠番になる。受付後に取消して別の日に打ち直された場合、API には打ち直し後の預り日の伝票だけが入る。
- **定休日**: 毎週木曜は全店定休でデータが無い。火曜などの店舗別定休は `store_closed_days` マスタを参照。営業日なのにデータが無い日は `journal_download_notes` を参照。
- **氏名の照合**: `customer_name` の完全一致・部分一致・グループ化は DB の照合順序 `utf8mb4_unicode_ci` に従う。
  - 同一視されるもの: 全角スペースと半角スペース、末尾の空白の有無、ひらがなとカタカナ、半角カナと全角カナ、英数字の全角/半角・大文字/小文字
  - 区別されるもの: **スペースの有無**（`山田 太郎` と `山田太郎` は別の顧客名として扱う）
  - 元データの表記は取り込み時に統一していない（前後の空白の除去のみ）。同一人物が複数の表記で入っていることがある。
- **氏名が空の行**: 顧客を指定せずに発行された伝票（金券の販売、新規入会・会員登録料など）。`customer_name` は空文字。
- **`id` の一意性**: `id` は `intake_items` の主キーで、全エンドポイント共通・一意。再取り込みは「既存行はスキップ、無い行だけ追加」のため、同じ行の `id` は変わらない。管理画面から手動削除された行の `id` は欠番になる。
- **個人情報保護**: `customer_name` は CSV 由来の表記揺れがあるため、検索は厳密一致 or LIKE のみ。名寄せ機能は提供しない。
- **量集計の精度**: `total_amount` は税込売価の単純合計。返品・修正の概念は未反映。
- **タイムゾーン**: `imported_at` などの datetime は JST (`+09:00`) または UTC 表記が混在し得る。`returned_at` は常に `+09:00` 付き。日付フィールド (`intake_date` 等) は JST 基準の純粋な date 型。
- **返却済にならない品目**: 返却 CSV に載っていても、`intake_items` に伝票ごと無い品目（預り日 CSV の取得後に、前日以前の預り日で登録された伝票など）は API に現れない。取り込み時に件数と内容を `/var/log/factory-shipping/import-returns.log` に記録している。
- **データ範囲**: 売上台帳ログから取り込まれた範囲のみ。半蔵側のリトライ失敗日は `journal_download_notes` を参照。
- **可用性**: factory-intake-shipping (gunicorn + nginx) の稼働に依存。冗長化なし。

---

## 11. 連絡先・関連ドキュメント

- 売上台帳ログ取込フロー: [SALES_ANALYSIS_DETAILED_DESIGN.md](SALES_ANALYSIS_DETAILED_DESIGN.md)
- 入荷データテーブル仕様: [INTAKE_LIST_SPEC.md](INTAKE_LIST_SPEC.md)
- 実装コード: [factory_shipping/analytics_api/](../factory_shipping/analytics_api/)
- 監査ログ: `/var/www/html/factory-intake-shipping/log/analytics_api_audit.log`
