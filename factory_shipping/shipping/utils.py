"""
出荷機能 - ユーティリティ関数

バーコード処理などの共通ロジック
"""


def parse_tag_barcode(code: str) -> tuple[str, str]:
    """
    9桁バーコードから店舗コードとタグ番号を取り出す

    NW-7(Code 2 of 7)形式のバーコードを想定。

    構成:
        - 1〜3桁目: 店舗コード (例: "024")
        - 4桁目: チェックデジット（現時点では検証せず無視）
        - 5〜8桁目: タグ本体 (4桁)
        - 9桁目: チェックデジット（現時点では検証せず無視）

    タグ番号の表記:
        内部的には "4-212" 形式に変換する。
        先頭1桁 + "-" + 残り3桁

    Args:
        code (str): 9桁のバーコード文字列

    Returns:
        tuple[str, str]: (店舗コード, タグ番号)

    Raises:
        ValueError: バーコードが9桁でない、または数字でない場合

    Examples:
        >>> parse_tag_barcode("024642123")
        ("024", "4-212")

        >>> parse_tag_barcode("001599876")
        ("001", "9-987")
    """
    # バリデーション
    if not code:
        raise ValueError("バーコードが空です")

    # 前後の空白を削除
    code = code.strip()

    # 長さチェック
    if len(code) != 9:
        raise ValueError(f"バーコードは9桁である必要があります（入力: {len(code)}桁）")

    # 数字チェック
    if not code.isdigit():
        raise ValueError("バーコードは数字のみで構成されている必要があります")

    # 店舗コード: 1〜3桁目
    store_code = code[0:3]

    # タグ番号: 5〜8桁目（4桁目はチェックデジット）
    tag_digits = code[4:8]

    # タグ番号を "X-YYY" 形式に変換
    tag_number = f"{tag_digits[0]}-{tag_digits[1:4]}"

    return store_code, tag_number


def validate_barcode_checkdigit(code: str) -> bool:
    """
    バーコードのチェックデジットを検証する（将来実装用）

    現時点では常に True を返す。
    将来的に NW-7 のチェックデジット検証ロジックを実装する場合はここに記述。

    Args:
        code (str): 9桁のバーコード文字列

    Returns:
        bool: チェックデジットが正しければ True
    """
    # TODO: NW-7 チェックデジット検証ロジックを実装
    return True
