# lang_processor

#250919tasks
#lang_processorディレクトリからresourcepacksやmodsへのアクセスを相対参照に変更（1階層上位へ移動する処理）
#kanjiconvライブラリを使用して、日本語化リソースパックを含むすべてのja_jp.jsonファイルのvalueに用いられている漢字をひらがなに変換（区切り文字は半角スペースを指定）するオプション処理を追加
#上記ライブラリのインストールが必要な場合、docker仮想環境を構築するdockerfileを作成
#translateのsleep_timeはデフォルトで3600秒となっているが、3600 - (end_time - start_time)とする
#translateプロンプトの再考
  #説明文の難しい表現
  #。があったら改行する？（ただし、。の後ろが"の場合は改行しない）
#リソースパック名にver名を追加？
#データパック等の構造を確認し、下記のようなハードコーディングによる名前定義が存在するかを捜索するスクリプト考案
summon zombie ~ ~1 ~ {CustomName:'{"text":"My Custom Zombie","color":"red","bold":true}',CustomNameVisible:1b,Tags:["named_mob"]}
#一時保存したtransrate済のja_jp.jsonファイルで用いた翻訳ルール、言語を統一して用いる処理（辞書として読み込ませる？）を実装
  #例 owner: 所有者 != owner: 持ち主
