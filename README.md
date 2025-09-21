# lang_processor

#250919tasks
【変更点】
#lang_processorディレクトリから1階層上位のフォルダに存在するresourcepacksやmodsへのアクセスを絶対参照から相対参照に変更
#kanjiconvライブラリを使用して、日本語化リソースパックを含むすべてのja_jp.jsonファイルのvalueに用いられている漢字をひらがなに変換（区切り文字は半角スペースを指定）するオプション処理を追加
#kanjiconvライブラリのインストールが必要な場合、docker仮想環境を構築するdockerfileを作成
#translateのsleep_timeはデフォルトで3600秒となっているが、処理開始から3600秒待つ処理に変更するため、3600 - (end_time - start_time)とする
#リソースパック名に自動でver名を付与する処理を実装（例:1.0.1のような形式）

【プロンプトの再考】
#説明文の表現を、対象年齢12歳程度のゲームの説明としてふさわしい簡易な表現に
#。があったらminecraftのエスケープシーケンスで改行処理（ただし、。の後ろが"の場合は改行しない）
#一時保存したtransrate済のja_jp.jsonファイルで用いた翻訳ルール、言語を統一して用いる処理（辞書として読み込ませる？）を実装
  #例 owner: 所有者 != owner: 持ち主

【追加検討事項】
#データパック等の構造を確認し、下記のようなハードコーディングによる名前定義が存在するかを捜索するスクリプト考案
summon zombie ~ ~1 ~ {CustomName:'{"text":"My Custom Zombie","color":"red","bold":true}',CustomNameVisible:1b,Tags:["named_mob"]}

