# 画面権限一覧

このドキュメントは、プロジェクト内のすべての画面（ルート）とその権限設定を一覧化したものです。

最終更新日: 2025-12-30

## 権限の種類

| 権限レベル | 説明 | デコレータ |
|-----------|------|-----------|
| **認証不要** | ログイン不要でアクセス可能 | なし |
| **ログイン必須** | ログインしているユーザーなら誰でもアクセス可能 | `@login_required` |
| **管理者権限** | `is_admin=True` のユーザーのみアクセス可能 | `@admin_required` |
| **店舗スタッフ権限** | `is_store_staff=True` のユーザーのみアクセス可能 | `@store_staff_required`（現在未使用） |

---

## 認証機能 (`/auth`)

| ルート | メソッド | 権限 | 説明 |
|--------|---------|------|------|
| `/login` | GET, POST | 認証不要 | ログイン画面 |
| `/logout` | GET | ログイン必須 | ログアウト |
| `/profile` | GET | ログイン必須 | プロフィール表示 |
| `/change_password` | GET, POST | ログイン必須 | パスワード変更 |

---

## メイン機能 (`/`)

| ルート | メソッド | 権限 | 説明 |
|--------|---------|------|------|
| `/` | GET | ログイン必須 | ダッシュボード（ホーム画面） |
| `/dashboard` | GET | ログイン必須 | ダッシュボード |
| `/features` | GET | ログイン必須 | 機能一覧ページ |
| `/set-operator` | POST | ログイン必須 | セッションに担当者を設定（API） |

---

## 入荷機能 (`/intake`)

| ルート | メソッド | 権限 | 説明 |
|--------|---------|------|------|
| `/intake/` | GET | ログイン必須 | 入荷データ一覧（旧） |
| `/intake/list` | GET, POST | ログイン必須 | 入荷一覧画面（ページング＋検索＋バーコード出荷対応） |
| `/intake/upload` | GET, POST | ログイン必須 | CSVファイルアップロード |
| `/intake/toggle-shipment/<item_id>` | POST | ログイン必須 | 出荷状態をトグル（未出荷 ↔ 出荷済み） |
| `/intake/detail/<item_id>` | GET | ログイン必須 | 入荷データ詳細 |
| `/intake/import-status` | GET | ログイン必須 | 入荷データ（売上台帳ログ）取得状況画面 |
| `/intake/fetch-csv-progress/<date_str>` | GET | ログイン必須 | CSVダウンロードの進捗状況を取得（API） |
| `/intake/fetch-csv/<date_str>` | POST | ログイン必須 | 指定日付のCSVをhanjowサイトからダウンロードして取り込む（API） |
| `/intake/<item_id>/history` | GET | ログイン必須 | 入荷アイテムの履歴を取得（API） |

---

## 出荷機能 (`/shipping`)

| ルート | メソッド | 権限 | 説明 |
|--------|---------|------|------|
| `/shipping/` | GET | ログイン必須 | 出荷スキャン画面 |
| `/shipping/scan` | POST | ログイン必須 | バーコードスキャン処理（API） |
| `/shipping/history` | GET | ログイン必須 | 出荷履歴 |
| `/shipping/process` | GET, POST | ログイン必須 | 出荷処理画面（バーコードスキャンまたは手動入力） |
| `/shipping/change-status/<item_id>` | POST | ログイン必須 | 商品の状態を変更（API） |

---

## ステータス確認機能 (`/status`)

| ルート | メソッド | 権限 | 説明 |
|--------|---------|------|------|
| `/status/` | GET | ログイン必須 | ステータス一覧（ダッシュボード） |
| `/status/unshipped` | GET | ログイン必須 | 未出荷一覧（status_idがshipped以外） |
| `/status/delayed` | GET | ログイン必須 | 遅れ品管理（未入荷商品を遅れ品ステータスに変更して工場請求） |
| `/status/update-intake-status/<item_id>` | POST | ログイン必須 | 入荷状態を更新する（工場請求中に変更）（API） |
| `/status/store/<store_code>` | GET | ログイン必須 | 店舗別ステータス |

---

## 監視機能 (`/monitoring`)

| ルート | メソッド | 権限 | 説明 |
|--------|---------|------|------|
| `/monitoring/` | GET | ログイン必須 | monitoringページ - cronジョブの実行状況一覧 |
| `/monitoring/log/<job_index>` | GET | ログイン必須 | ログファイルの内容を表示（最終100行） |
| `/monitoring/error-log/<job_index>` | GET | ログイン必須 | エラーログファイルの内容を表示（最終100行） |
| `/monitoring/app-log/<log_index>` | GET | ログイン必須 | アプリケーションログファイルの内容を表示（最終200行） |

---

## 管理者機能 (`/admin`)

**すべてのルートが `@admin_required` で保護されています（管理者権限必須）**

### ダッシュボード

| ルート | メソッド | 権限 | 説明 |
|--------|---------|------|------|
| `/admin/` | GET | 管理者権限 | 管理者ダッシュボード |

### ユーザー管理

| ルート | メソッド | 権限 | 説明 |
|--------|---------|------|------|
| `/admin/users` | GET | 管理者権限 | ユーザー一覧 |
| `/admin/users/create` | GET, POST | 管理者権限 | ユーザー作成 |
| `/admin/users/<user_id>/edit` | GET, POST | 管理者権限 | ユーザー編集 |
| `/admin/users/<user_id>/delete` | POST | 管理者権限 | ユーザー削除 |

### 商品状態管理

| ルート | メソッド | 権限 | 説明 |
|--------|---------|------|------|
| `/admin/item-statuses` | GET | 管理者権限 | 商品状態一覧 |
| `/admin/item-statuses/create` | GET, POST | 管理者権限 | 商品状態作成 |
| `/admin/item-statuses/<status_id>/edit` | GET, POST | 管理者権限 | 商品状態編集 |
| `/admin/item-statuses/<status_id>/delete` | POST | 管理者権限 | 商品状態削除 |

### 店舗管理

| ルート | メソッド | 権限 | 説明 |
|--------|---------|------|------|
| `/admin/stores` | GET | 管理者権限 | 店舗一覧 |
| `/admin/stores/create` | GET, POST | 管理者権限 | 店舗作成 |
| `/admin/stores/<store_id>/edit` | GET, POST | 管理者権限 | 店舗編集 |
| `/admin/stores/<store_id>/delete` | POST | 管理者権限 | 店舗削除 |

### 入荷データ管理

| ルート | メソッド | 権限 | 説明 |
|--------|---------|------|------|
| `/admin/intake-items` | GET | 管理者権限 | 入荷データ一覧（全件表示） |
| `/admin/intake-items/create` | GET, POST | 管理者権限 | 入荷データ作成 |
| `/admin/intake-items/<item_id>/edit` | GET, POST | 管理者権限 | 入荷データ編集 |
| `/admin/intake-items/<item_id>/delete` | POST | 管理者権限 | 入荷データ削除 |

### 出荷ログ管理

| ルート | メソッド | 権限 | 説明 |
|--------|---------|------|------|
| `/admin/shipment-logs` | GET | 管理者権限 | 出荷ログ一覧 |
| `/admin/shipment-logs/create` | GET, POST | 管理者権限 | 出荷ログ作成 |
| `/admin/shipment-logs/<log_id>/edit` | GET, POST | 管理者権限 | 出荷ログ編集 |
| `/admin/shipment-logs/<log_id>/delete` | POST | 管理者権限 | 出荷ログ削除 |

### 遅れ品管理

| ルート | メソッド | 権限 | 説明 |
|--------|---------|------|------|
| `/admin/delayed-items` | GET | 管理者権限 | 遅れ品一覧 |
| `/admin/delayed-items/create` | GET, POST | 管理者権限 | 遅れ品作成 |
| `/admin/delayed-items/<item_id>/edit` | GET, POST | 管理者権限 | 遅れ品編集 |
| `/admin/delayed-items/<item_id>/delete` | POST | 管理者権限 | 遅れ品削除 |

---

## 権限設定の実装詳細

### デコレータの実装

権限チェックは以下のデコレータで実装されています：

- **`@login_required`** (Flask-Login)
  - ログインしていない場合は `/login` にリダイレクト

- **`@admin_required`** (`factory_shipping/admin/decorators.py`)
  - ログインしていない場合は `/login` にリダイレクト
  - ログインしているが `is_admin=False` の場合は 403 エラー

- **`@store_staff_required`** (`factory_shipping/admin/decorators.py`)
  - ログインしていない場合は `/login` にリダイレクト
  - ログインしているが `is_store_staff=False` の場合は 403 エラー
  - **注意**: 現在、このデコレータを使用しているルートはありません

### 権限の組み合わせ

- 管理者権限と店舗スタッフ権限は独立して設定可能
- 両方の権限を持つユーザーも作成可能
- 管理者権限を持つユーザーは、すべての管理者機能にアクセス可能

---

## 統計情報

- **認証不要**: 1ルート（`/login`）
- **ログイン必須**: 約40ルート
- **管理者権限必須**: 25ルート
- **店舗スタッフ権限必須**: 0ルート（現在未使用）

---

## 注意事項

1. **管理者権限の重要性**
   - 管理者権限を持つユーザーは、すべてのデータを閲覧・編集・削除できます
   - ユーザー管理機能も含めて、システム全体を制御できます

2. **店舗スタッフ権限**
   - 現在、`@store_staff_required` デコレータは実装されていますが、使用されていません
   - 将来的に店舗スタッフ専用の機能を追加する場合は、このデコレータを使用してください

3. **APIエンドポイント**
   - 多くのAPIエンドポイント（JSONレスポンスを返すルート）も `@login_required` で保護されています
   - フロントエンドから呼び出す際は、ログインセッションが必要です

---

## 更新履歴

- 2024年: 初版作成



