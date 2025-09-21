#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import json
import zipfile
import argparse
import subprocess
import time
import logging
import glob
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

# --- ロギング設定 ---
# ログファイルはスクリプトと同じディレクトリに保存
log_file_path = Path(__file__).parent / 'translation_log.txt'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file_path, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class MinecraftLangProcessor:
    """
    MinecraftのModやデータパックの言語ファイルを処理し、翻訳作業を支援する統合ツール。
    - MOD/データパックからの言語ファイル抽出
    - 既存翻訳との差分検出
    - Gemini CLIによる自動翻訳
    - 翻訳リソースパックの構築
    """

    def __init__(self, instance_path: str):
        """
        コンストラクタ

        Args:
            instance_path (str): Minecraftインスタンスのルートパス。
        """
        # --- パス設定 ---
        self.instance_path = Path(instance_path)
        if not self.instance_path.is_dir():
            logger.error(f"指定されたインスタンスパスが見つかりません: {self.instance_path}")
            raise FileNotFoundError(f"指定されたインスタンスパスが見つかりません: {self.instance_path}")

        self.work_dir = self.instance_path / "lang_processer"
        self.mods_path = self.instance_path / "mods"
        self.datapacks_path = self.instance_path / "datapacks"
        self.resource_packs_path = self.instance_path / "resourcepacks"

        # 作業ディレクトリ
        self.lang_diff_path = self.work_dir / "lang_diff"
        self.untranslated_path = self.work_dir / "untranslated"
        self.translated_path = self.work_dir / "translated"
        self.progress_path = self.work_dir / "progress" # 翻訳の進捗保存用

        # --- 翻訳設定 ---
        self.dictionary_path = self.work_dir / "my_custom_dictionary.json"
        self.translation_chunk_size = 1500
        self.translation_wait_time = 3600  # チャンク間の待機時間（秒）

        # --- リソースパック設定 ---
        self.resource_pack_name = "CobbleverseJapaneseLangPack"
        self.pack_format = 48  # Minecraft 1.21.x
        self.pack_description = "Adds Japanese translations for Cobblemon and other mods."

        self._setup_directories()
        self._initialize_dictionary()

    def _setup_directories(self):
        """必要な作業ディレクトリを作成する。"""
        for path in [self.work_dir, self.lang_diff_path, self.untranslated_path, 
                     self.translated_path, self.progress_path]:
            path.mkdir(exist_ok=True)
        logger.info(f"作業ディレクトリを準備しました: {self.work_dir}")

    def _initialize_dictionary(self):
        """カスタム辞書ファイルが存在しない場合に初期化する。"""
        if not self.dictionary_path.exists():
            logger.info(f"カスタム辞書ファイルが見つからないため、テンプレートを作成します: {self.dictionary_path}")
            template = {
                "Cobblemon": "コブルモン",
                "Pikachu": "ピカチュウ",
                "Pokeball": "モンスターボール"
            }
            self._save_json(template, self.dictionary_path)

    def _get_latest_file(self, directory: Path, prefix: str) -> Optional[Path]:
        """指定されたディレクトリとプレフィックスに一致する最も新しいファイルを返す。"""
        files = list(directory.glob(f"{prefix}_*.json"))
        if not files:
            return None
        return max(files, key=lambda f: f.stat().st_mtime)

    def _save_json(self, data: Dict, filepath: Path):
        """JSONデータを指定されたパスに保存する。"""
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            logger.info(f"ファイルを保存しました: {filepath}")
        except Exception as e:
            logger.error(f"JSONファイルの保存に失敗しました: {filepath} - {e}")

    def _load_json(self, file_path: Path) -> Optional[Dict]:
        """JSONファイルを読み込む。"""
        if not file_path.exists():
            logger.error(f"ファイルが見つかりません: {file_path}")
            return None
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"JSONの解析に失敗しました: {file_path} - {e}")
            return None
        except Exception as e:
            logger.error(f"ファイルの読み込みに失敗しました: {file_path} - {e}")
            return None

    def _extract_lang_from_zip(self, zip_path: Path, all_en_us: Dict, all_ja_jp: Dict):
        """単一のzipファイルから言語ファイルを抽出する。"""
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for filename in zf.namelist():
                    if not (filename.endswith('en_us.json') or filename.endswith('ja_jp.json')):
                        continue
                    
                    # assets/<namespace>/lang/<lang_code>.json
                    if "assets" not in filename or "lang" not in filename:
                        continue

                    try:
                        with zf.open(filename) as f:
                            data = json.load(f)
                            target_dict = all_en_us if filename.endswith('en_us.json') else all_ja_jp
                            for key, value in data.items():
                                if isinstance(value, str):
                                    target_dict[key] = value.replace("'", "''")
                    except (json.JSONDecodeError, UnicodeDecodeError) as e:
                        logger.warning(f"  - {zip_path.name}内の{filename}の読み込みに失敗: {e}")
        except zipfile.BadZipFile:
            logger.warning(f"  - {zip_path.name}は有効なzipファイルではありません。")
        except Exception as e:
            logger.error(f"  - {zip_path.name}の処理中に予期せぬエラー: {e}")

    def extract_lang_diff(self):
        """
        処理1: Modとデータパックからen_us.jsonとja_jp.jsonを抽出し、差分を作成する。
        """
        logger.info("処理1: Mod/データパック言語ファイルの差分抽出を開始します...")
        all_en_us: Dict[str, str] = {}
        all_ja_jp: Dict[str, str] = {}

        # modsフォルダから抽出
        if self.mods_path.exists():
            logger.info(f"modsフォルダを処理中: {self.mods_path}")
            for mod_file in self.mods_path.glob("*.jar"):
                logger.info(f"  - {mod_file.name} を処理中...")
                self._extract_lang_from_zip(mod_file, all_en_us, all_ja_jp)
        else:
            logger.warning(f"modsフォルダが見つかりません: {self.mods_path}")

        # datapacksフォルダから抽出
        if self.datapacks_path.exists():
            logger.info(f"datapacksフォルダを処理中: {self.datapacks_path}")
            for datapack_file in self.datapacks_path.rglob("*.zip"):
                logger.info(f"  - {datapack_file.relative_to(self.datapacks_path)} を処理中...")
                self._extract_lang_from_zip(datapack_file, all_en_us, all_ja_jp)
        else:
            logger.warning(f"datapacksフォルダが見つかりません: {self.datapacks_path}")

        diff_keys = set(all_en_us.keys()) - set(all_ja_jp.keys())
        all_diff = {key: all_en_us[key] for key in sorted(list(diff_keys)) if key in all_en_us}

        logger.info(f"en_usから {len(all_en_us)} 個のキーを収集しました。")
        logger.info(f"ja_jpから {len(all_ja_jp)} 個のキーを収集しました。")
        logger.info(f"差分（未翻訳）キーが {len(all_diff)} 個見つかりました。")

        date_str = datetime.now().strftime('%y%m%d')
        diff_filename = f"all_diff_{date_str}.json"
        self._save_json(all_diff, self.lang_diff_path / diff_filename)
        logger.info("処理1が完了しました。")

    def find_untranslated(self):
        """
        処理2: 翻訳が必要なファイルを抽出する。
        """
        logger.info("処理2: 未翻訳ファイルの抽出を開始します...")
        latest_diff_file = self._get_latest_file(self.lang_diff_path, "all_diff")
        if not latest_diff_file:
            logger.error("all_diff_yymmdd.jsonファイルが見つかりません。先に処理1を実行してください。")
            return

        all_diff = self._load_json(latest_diff_file)
        if all_diff is None: return

        # 既存の日本語化リソースパックを探す
        existing_pack_path = self.resource_packs_path / self.resource_pack_name
        existing_lang_file = existing_pack_path / "assets" / "minecraft" / "lang" / "ja_jp.json"

        if not existing_lang_file.exists():
            logger.info("既存の日本語化リソースパックが見つかりませんでした。差分全体を未翻訳とします。")
            untranslated_dict = all_diff
        else:
            logger.info(f"既存のリソースパック {self.resource_pack_name} を検出")
            translated = self._load_json(existing_lang_file) or {}

            already_translated_keys = {k for k, v in translated.items() if v}
            keys_to_translate = set(all_diff.keys()) - already_translated_keys
            untranslated_dict = {key: all_diff[key] for key in sorted(list(keys_to_translate))}
            
            logger.info(f"リソースパックから {len(translated)} 個の翻訳済みキーを読み込みました。")
            logger.info(f"差分 {len(all_diff)} 件のうち、真に未翻訳のキーは {len(untranslated_dict)} 件です。")

        date_str = datetime.now().strftime('%y%m%d')
        untranslated_filename = f"all_untranslated_{date_str}.json"
        self._save_json(untranslated_dict, self.untranslated_path / untranslated_filename)
        logger.info("処理2が完了しました。")

    def auto_translate(self, resume_chunk: Optional[int] = None):
        """
        処理3: 未翻訳ファイルをGemini CLIで自動翻訳する。
        """
        logger.info("処理3: 自動翻訳処理を開始します...")
        latest_untranslated_file = self._get_latest_file(self.untranslated_path, "all_untranslated")
        if not latest_untranslated_file:
            logger.error("未翻訳ファイルが見つかりません。先に処理1, 2を実行してください。")
            return

        data_to_translate = self._load_json(latest_untranslated_file)
        if not data_to_translate:
            logger.info("翻訳対象のキーが0件のため、処理を終了します。")
            return

        date_str = datetime.now().strftime('%y%m%d')
        output_filename = self.translated_path / f"all_translated_{date_str}.json"
        
        logger.info(f"入力ファイル: {latest_untranslated_file}")
        logger.info(f"出力ファイル: {output_filename}")
        logger.info(f"総項目数: {len(data_to_translate)}")

        chunks = self._create_chunks(data_to_translate)
        translated_data = {}
        start_chunk = 1

        if resume_chunk and resume_chunk > 1:
            progress_file_to_load = self.progress_path / f"progress_{resume_chunk - 1}.json"
            if progress_file_to_load.exists():
                logger.info(f"{progress_file_to_load} から進捗を読み込みます")
                translated_data = self._load_json(progress_file_to_load) or {}
                start_chunk = resume_chunk
                logger.info(f"チャンク {start_chunk} から処理を再開します")
            else:
                logger.warning(f"進捗ファイル {progress_file_to_load} が見つかりません。最初から処理を開始します。")

        for i, chunk in enumerate(chunks, 1):
            if i < start_chunk:
                continue

            logger.info(f"チャンク {i}/{len(chunks)} を処理中...")
            try:
                translated_chunk = self._call_gemini_cli(chunk)
                translated_data.update(translated_chunk)
                
                progress_file = self.progress_path / f"progress_{i}.json"
                self._save_json(translated_data, progress_file)
                
                if i < len(chunks):
                    logger.info(f"{self.translation_wait_time}秒間待機します...")
                    time.sleep(self.translation_wait_time)
            except Exception as e:
                logger.error(f"チャンク {i} の処理でエラー: {e}")
                logger.info("このチャンクはスキップされ、元のデータが使用されます。")
                translated_data.update(chunk) # エラー時は元データを保持
                continue
        
        self._save_json(translated_data, output_filename)
        logger.info("すべての翻訳処理が完了しました。")
        self._cleanup_progress_files()

    def _create_chunks(self, data: Dict) -> List[Dict]:
        """データをチャンクに分割する。"""
        items = list(data.items())
        chunks = [dict(items[i:i + self.translation_chunk_size]) for i in range(0, len(items), self.translation_chunk_size)]
        logger.info(f"データを{len(chunks)}個のチャンクに分割しました (チャンクサイズ: {self.translation_chunk_size})")
        return chunks

    def _call_gemini_cli(self, input_data: Dict) -> Dict:
        """Gemini CLIを呼び出して翻訳を実行する。"""
        prompt = self._build_translation_prompt()
        input_json = json.dumps(input_data, ensure_ascii=False, indent=2)
        full_prompt = f"{prompt}\n\n翻訳対象のJSON:\n```json\n{input_json}\n```\n"
        
        cmd = ['gemini', 'chat']
        logger.info(f"Gemini CLIを実行中... (項目数: {len(input_data)})")
        
        try:
            process = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8'
            )
            stdout, stderr = process.communicate(input=full_prompt)

            if process.returncode != 0:
                logger.error(f"Gemini CLIエラー: {stderr}")
                raise RuntimeError(f"Gemini CLI failed: {stderr}")

            response_text = stdout.strip()
            if '```json' in response_text:
                json_start = response_text.find('```json') + 7
                json_end = response_text.rfind('```')
                json_text = response_text[json_start:json_end].strip()
            elif response_text.startswith('{'):
                json_text = response_text
            else:
                logger.warning("レスポンスにJSONが見つかりません。元のデータを返します。")
                return input_data

            translated_data = json.loads(json_text)
            logger.info(f"翻訳完了: {len(translated_data)}項目")
            return translated_data

        except json.JSONDecodeError as e:
            logger.error(f"レスポンスのJSON解析失敗: {e}\nレスポンス内容: {stdout}")
            return input_data # 解析失敗時は元データを返す
        except Exception as e:
            logger.error(f"Gemini CLI呼び出し中にエラー: {e}")
            raise

    def _build_translation_prompt(self) -> str:
        """翻訳用のプロンプトを構築する。"""
        return f"""あなたは、Minecraftやポケモンのゲームに関する深い知識を持つ、経験豊富なディレクター兼プロの翻訳家です。あなたの仕事は、与えられたJSONファイル内の英語のテキストを、自然で文脈に合った日本語に翻訳することです。

        **あなたの役割と能力:**
        *   **ディレクター:** Minecraftとポケモンの両シリーズについて、開発者レベルの知識、語彙、ストーリー、世界観を熟知しています。
        *   **プロの翻訳家:** ゲーム内の英単語や英文を、ゲームの文脈に沿った、違和感のない自然な日本語に翻訳する専門家です。

        **タスク:**
        以下のJSONデータに含まれるすべての英語の`value`を、日本語に翻訳してください。

        **重要な指示:**
        *   **カスタム辞書の適用:** 翻訳の際には、必ず `{self.dictionary_path}` にあるカスタム辞書のルールを適用してください。この辞書には、Minecraftやポケモンの固有名詞に関する重要な翻訳ルールが含まれています。
        *   **正確性と自然さ:** 翻訳は、元の意味を正確に伝えつつ、日本のプレイヤーにとって自然で没入感のある表現になるように心がけてください。
        *   **翻訳方針の区別:** 以下の方針を区別して適用してください:
            - **キャラクターのセリフ:** 話者の設定はすべて12歳程度の少年少女とし、年齢相応の平易かつカジュアルな語彙を用い、親しみやすく、中性的な口調で、文脈に合った自然な日本語に翻訳してください。例: "Hey there!" → "やあ！"
            - **一般的なテキスト:** ゲーム内の説明文、メニューオプション、チュートリアルなどの一般的なテキストは、文脈に合った自然な日本語に翻訳してください。
        *   **JSON形式の維持:** 翻訳後のデータは、元のJSONと同じ構造を維持してください。キーは変更せず、`value`のみを翻訳してください。
        *   **出力形式:** 翻訳結果は、必ず以下のようなマークダウンのJSONコードブロック形式で返してください。

            ```json
            {{
            "key1": "翻訳されたvalue1",
            "key2": "翻訳されたvalue2",
            ...
            }}
            ```

        あなたの専門知識を最大限に活かして、最高品質の翻訳をお願いします。"""

    def _cleanup_progress_files(self):
        """進捗ファイルをクリーンアップする。"""
        try:
            progress_files = list(self.progress_path.glob("progress_*.json"))
            if not progress_files: return
            
            logger.info("進捗ファイルをクリーンアップします...")
            for file in progress_files:
                file.unlink()
                logger.info(f"進捗ファイルを削除: {file}")
        except Exception as e:
            logger.warning(f"進捗ファイルのクリーンアップに失敗: {e}")

    def build_resource_pack(self):
        """
        処理4: 翻訳済みファイルからリソースパックを構築する。
        """
        logger.info("処理4: リソースパックの構築を開始します...")
        latest_translated_file = self._get_latest_file(self.translated_path, "all_translated")
        if not latest_translated_file:
            logger.error("翻訳済みファイルが見つかりません。処理3を完了させてください。")
            return

        newly_translated_data = self._load_json(latest_translated_file)
        if newly_translated_data is None: return
        logger.info(f"今回翻訳したキーを {len(newly_translated_data)} 個読み込みました。")

        # --- リソースパックのパスを定義 ---
        output_pack_dir = self.resource_packs_path / self.resource_pack_name
        lang_dir = output_pack_dir / "assets" / "minecraft" / "lang"
        lang_file = lang_dir / "ja_jp.json"

        # --- 既存の翻訳を読み込む ---
        base_translations: Dict[str, str] = {}
        if lang_file.exists():
            logger.info(f"既存のリソースパック {self.resource_pack_name} をベースに結合します...")
            base_translations = self._load_json(lang_file) or {}
        
        logger.info(f"結合前の翻訳キー数: {len(base_translations)}")
        base_translations.update(newly_translated_data)
        logger.info(f"結合後の翻訳キー数: {len(base_translations)}")

        final_translations = dict(sorted(base_translations.items()))

        # --- ディレクトリとファイルの作成 ---
        logger.info(f"ディレクトリを作成中: {lang_dir}")
        lang_dir.mkdir(parents=True, exist_ok=True)

        # --- pack.mcmetaを作成 ---
        pack_mcmeta_file = output_pack_dir / "pack.mcmeta"
        pack_meta = {
            "pack": {
                "pack_format": self.pack_format,
                "description": self.pack_description
            }
        }
        self._save_json(pack_meta, pack_mcmeta_file)

        # --- ja_jp.jsonを作成 ---
        self._save_json(final_translations, lang_file)

        logger.info(f"リソースパック '{self.resource_pack_name}' が正常に作成/更新されました。")
        logger.info(f"場所: {output_pack_dir}")
        logger.info("処理4が完了しました。")

def main():
    """メイン実行関数"""
    # --- Minecraftインスタンスパスの指定 ---
    # このパスを環境に合わせて変更してください
    DEFAULT_INSTANCE_PATH = "/home/natori/.var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher/instances/COBBLEVERSE-PokemonAdventure[Cobblemon]/minecraft"

    parser = argparse.ArgumentParser(
        description="Minecraft Mod/データパック 日本語翻訳支援ツール",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "action",
        choices=["extract", "find", "translate", "build", "all"],
        help="""
実行するアクションを選択してください:
  extract   - (処理1) Mod/データパックから言語ファイルを抽出し、差分を作成します。
  find      - (処理2) 翻訳が必要なファイルを抽出します。
  translate - (処理3) 未翻訳ファイルをGeminiで自動翻訳します。
  build     - (処理4) 翻訳済みファイルからリソースパックを構築します。
  all       - (処理1～4) を連続して実行します。
"""
    )
    parser.add_argument("--instance_path", default=DEFAULT_INSTANCE_PATH, help="Minecraftインスタンスのパス")
    parser.add_argument("--resume", type=int, help="翻訳を中断した場合に、指定したチャンク番号から再開します。")

    args = parser.parse_args()
    
    try:
        processor = MinecraftLangProcessor(instance_path=args.instance_path)

        if args.action == "all":
            processor.extract_lang_diff()
            processor.find_untranslated()
            processor.auto_translate(resume_chunk=args.resume)
            processor.build_resource_pack()
        elif args.action == "extract":
            processor.extract_lang_diff()
        elif args.action == "find":
            processor.find_untranslated()
        elif args.action == "translate":
            processor.auto_translate(resume_chunk=args.resume)
        elif args.action == "build":
            processor.build_resource_pack()

    except FileNotFoundError as e:
        logger.error(e)
    except KeyboardInterrupt:
        logger.info("\n処理が中断されました。")
    except Exception as e:
        logger.critical(f"予期せぬエラーが発生しました: {e}", exc_info=True)

if __name__ == "__main__":
    main()
