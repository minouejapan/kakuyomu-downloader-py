#-------------------------------------------------------------------------------
#
# カクヨムテキストダウンローダー kakuyomudlpy.py
#
# ver1.0  2024/12/27 Pythonで一から書き直した
#                    ・正規表現処理を前提
#                    ・識別タグは定数宣言ではなくその場埋め込み(見晴らし優先)
#
#-------------------------------------------------------------------------------
import sys
#import requests
import codecs
import urllib.request
import html
import re
import time

# 青空文庫形式
AO_RBI = '｜'                # ルビのかかり始め(必ずある訳ではない)
AO_RBL = '《'                # ルビ始め
AO_RBR = '》'                # ルビ終わり
AO_TGI = '［＃'              # 青空文庫書式設定開始
AO_TGO = '］'                #        〃       終了
AO_CPI = '［＃「'            # 見出しの開始
AO_CPT = '」は大見出し］'    # 章
AO_SEC = '」は中見出し］'    # 話
AO_PRT = '」は小見出し］'

AO_CPB = '［＃大見出し］'
AO_CPE = '［＃大見出し終わり］'
AO_SEB = '［＃中見出し］'
AO_SEE = '［＃中見出し終わり］'
AO_PRB = '［＃小見出し］'
AO_PRE = '［＃小見出し終わり］'

AO_DAI = '［＃ここから'        # ブロックの字下げ開始
AO_DAO = '［＃ここで字下げ終わり］'
AO_DAN = '字下げ］'
AO_PGB = '［＃改丁］'        # 改丁と会ページはページ送りなのか見開き分の
AO_PB2 = '［＃改ページ］'    # 送りかの違いがあるがどちらもページ送りとする
AO_SM1 = '」に傍点］'        # ルビ傍点
AO_SM2 = '」に丸傍点］'      # ルビ傍点 どちらもsesami_dotで扱う
AO_EMB = '［＃丸傍点］'      # 横転開始
AO_EME = '［＃丸傍点終わり］'       # 傍点終わり
AO_KKL = '［＃ここから罫囲み］'     # 本来は罫囲み範囲の指定だが、前書きや後書き等を
AO_KKR = '［＃ここで罫囲み終わり］' # 一段小さい文字で表記するために使用する
AO_END = '底本：'            # ページフッダ開始（必ずあるとは限らない）
AO_PIB = '［＃リンクの図（'  # 画像埋め込み
AO_PIE = '）入る］'          # 画像埋め込み終わり
AO_LIB = '［＃リンク（'      # 画像埋め込み
AO_LIE = '）入る］'          # 画像埋め込み終わり
AO_CVB = '［＃表紙の図（'    # 表紙画像指定
AO_CVE = '）入る］'          # 終わり

# グローバル変数
page_list = []      # 各話のURL
# title_list = []   # 各話タイトル名
text_page = []      # 取り出したテキスト保管用
log_file = []       # ログファイル用
url = ''            # 引数で指定されたURL
filename = ''       # 作品タイトルから作成した保存ファイル名
pchapt = ''         # 章タイトル保存用
startn = 0          # DL開始番号


# HTMLファイルのダウンロード
def loadfromhtml(url: str) -> str:
    with urllib.request.urlopen(url) as res:
        html = res.read().decode()
    return html

# 本文内の余分なタグを除去する
def elimbodytags(base: str) -> str:
    tmp = re.sub('<.*?>', '', base)
    tmp = re.sub(' ', '', tmp)
    return tmp

# 改行タグを改行コードに変換する
def changebrks(base: str) -> str:
    return re.sub('<br />', '\r\n', base)

# 本文の青空文庫ルビ指定に用いられる文字があった場合誤作動しないように
# 青空文庫代替表記に変換する
def changeaozoratags(base: str) -> str:
    base = base.replace('<rp>《</rp>', '<rp>(</rp>')
    base = base.replace('<rp>》</rp>', '<rp>)</rp>')
    base = base.replace('《', '※［＃始め二重山括弧、1-1-52］')
    base = base.replace('》', '※［＃終わり二重山括弧、1-1-53］')
    base = base.replace('｜', '※［＃縦線、1-1-35］')
    return base

# 本文のルビタグを青空文庫形式に変換する
def changerubys(base: str) -> str:
    base = base.replace('<rp>(</rp>', '')
    base = base.replace('<rp>)</rp>', '')
    base = base.replace('<rp>（</rp>', '')
    base = base.replace('<rp>）</rp>', '')
    base = base.replace('<rb>', '')
    base = base.replace('</rb>', '')
    # rubyタグを青空文庫形式に変換
    base = base.replace('<ruby>', AO_RBI)
    base = base.replace('<rt>',   AO_RBL)
    base = base.replace('</rt></ruby>', AO_RBR)
    # カクヨムの傍点タグ？
    base = base.replace('<em class="emphasisDots"><span>', AO_EMB)
    base = base.replace('<span>', AO_EMB)
    base = base.replace('</span></em>', AO_EME)
    base = base.replace('</span>', AO_EME)
    return base

# HTML特殊文字の処理
# 1)エスケープ文字列 → 実際の文字
# 2)&#x???? → 通常の文字
def restore2realchar(base: str) -> str:
    # エスケープされた文字
    base = base.replace('&lt',      '<')
    base = base.replace('&gt',      '>')
    base = base.replace('&quot',    '')
    base = base.replace('&nbsp',    ' ')
    base = base.replace('&yen',     '\\')
    base = base.replace('&brvbar',  '|')
    base = base.replace('&copy',    '©')
    base = base.replace('&amp',     '&')
    # &#????にエンコードされた文字をデコードする
    en = re.search(r'&#.*?;', base)
    while en:
        ch = en.group(0)
        de = html.unescape(ch)     # &#????;を文字に戻す
        re.sub(ch, de, base)
        en = re.search(r'&#.*?;', base)
    return base

# 埋め込まれた画像リンクを青空文庫形式に変換する
def changeimages(base: str) -> str:
    base = base.replace('<a href="', AO_PIB)
    base = base.replace(' alt="挿絵" name="img">【挿絵表示】</a>', AO_PIE)
    return base

# タイトル名をファイル名として使用出来るかどうかチェックし、使用不可文字が
# あれば修正する('-'に置き換える)
def pathfilter(title: str) -> str:
    title = title.replace('\\', '-')
    title = title.replace('/', '-')
    title = title.replace(';', '-')
    title = title.replace(':', '-')
    title = title.replace('*', '-')
    title = title.replace('?', '-')
    title = title.replace('+', '-')
    title = title.replace('<', '-')
    title = title.replace('>', '-')
    title = title.replace('|', '-')
    title = title.replace('.', '-')
    title = title.replace('\t', '-')
    title = title.replace(' ', '-')
    if len(title) > 24:
        title = title[:24]
    return title

# タグ変換とフィルター実行
def tagfilter(line: str) -> str:
    tmp = changebrks(line)
    tmp = changerubys(tmp)
    tmp = changeimages(tmp)
    tmp = elimbodytags(tmp)
    tmp = restore2realchar(tmp)
    return tmp

# 連載状況取得
def getnovelstat(body: str) -> str:
    m = re.search('<div class="Meta_metaItem__8eZTP">.*?<!-- --> 全<!-- -->.*?<!-- -->話', body)
    stat = m.group(0)
    if stat.find('完結') != -1:
         return '【完結】'
    elif stat.find('連載中') != -1:
        return '【連載中】'
    else:
        return ''

# トップページの解析
def parsetoppage(body: str) -> int:
    # グローバル変数
    global filename, url, page_list, log_file, text_page #, title_list

    sys.stdout.write("小説情報を取得中 " + url + ' ... ')
    # 連載状況
    stat = getnovelstat(body)
    # タイトル
    m = re.search(r'<a title=".*?"', body)
    if m:
        title = re.sub('"', '', re.sub('<a title=''', '', m.group(0)))
    else:
        print('指定されたページからタイトル情報を取得出来ませんでした.')
        return -1
    # 作者URL・作者名
    m = re.search(r'<div class="partialGift.*?"><a href=".*?" .*?">.*?</a>', body)
    if m:
        authurl = m.group(0)
        auther = authurl
        authurl = re.sub('<div class="partialGift.*?"><a href="', '', authurl)
        authurl = 'https://kakuyomu.jp/users/' + re.sub('" class="Link.*?">.*?</a>', '', authurl)
        auther = re.sub('<div class="partialGift.*?"><a href=".*?" class="Link.*?>', '', auther)
        auther = re.sub('</a>', '', auther)
    else:
        print('指定されたページから作者情報を取得出来ませんでした.')
        return -1
    # キャッチコピー
    m = re.search(r'"totalFollowers":.*?,"catchphrase":".*?","introduction":', body)
    if m:
        intro = m.group(0)
        intro = re.sub('","introduction":', "", re.sub('"totalFollowers":.*?,"catchphrase":"', '', intro))
    # 前書き
    m = re.search(r'"totalFollowers":.*?,"catchphrase":".*?","introduction":".*?",', body)
    if m:
        intro = intro + '\r\n\r\n' + re.sub('","', "", re.sub('"totalFollowers":.*?,"catchphrase":".*?","introduction":"', '', m.group(0)))
    # 目次情報を取得する
    ep = re.search(r'"__typename":"Episode","id":".*?","title":".*?",', body)
    if not ep:
        print('指定されたページからエピソード情報を取得出来ませんでした.')
        return -1
    while ep:
        tmp = ep.group(0)
        # URLを切り出す
        purl = re.sub('"__typename":"Episode","id":"', '', tmp)
        purl = url + '/episodes/' + re.sub('","title":".*?",', '', purl)
        # エピソードタイトルを切り出す
        epsd = re.sub('"__typename":"Episode","id":".*?","title":"','', tmp)
        epsd = re.sub('",', '',epsd)
        body = body[ep.end(0):] # 切り出した部分までを除去して次のタイトルを検索する
        page_list.append(purl)
        # title_list.append(epsd) エピソードタイトルは各ページから取り出すので使わない
        ep = re.search('"__typename":"Episode","id":".*?","title":".*?",', body)
    # ファイル名が指定されていなければ、ファイル名・ログファイル・DLテキストを構成する
    if filename == '':
        filename = pathfilter(title) + '.txt'
        if stat == '【完結】':
            if filename.find('完結') == -1:
                filename = stat + filename
        else:
            filename = stat + filename

    log_file.append('小説URL :' + url + '\r\n')
    log_file.append('タイトル:' + title + '\r\n')
    log_file.append('作者    :' + auther + '\r\n')
    log_file.append('作者URL :' + authurl + '\r\n')
    log_file.append('あらすじ' + '\r\n')
    log_file.append(intro + '\r\n')
    # ログファイルを保存する
    fout = codecs.open(filename + '.log', 'w', 'utf8')
    fout.writelines(log_file)
    fout.close()
    # 保存するテキストを準備する
    text_page.append(title + '\r\n')
    text_page.append(auther + '\r\n')
    text_page.append('あらすじ' + '\r\n')
    text_page.append(authurl + '\r\n')
    text_page.append(intro + '\r\n' + AO_PB2 + '\r\n')
    return 0

def parsepage(body: str) -> str:
    global text_page, pchapt # グローバル変数

    # 章タイトル
    chapt1 = re.search(r'<p class="chapterTitle level1 .*?<span>.*?</span>', body)
    # 章サブタイトル
    chapt2 = re.search(r'<p class="chapterTitle level2 .*?<span>.*?</span>', body)
    # 話タイトル
    sect   = re.search(r'<p class="widget-episodeTitle.*?">.*?</p>', body)
    # タイトルを構成する
    if chapt1:
        ch1 = chapt1.group(0)
        ch1 = re.sub('<p class="chapterTitle level1 .*?<span>', '', ch1)
        ch1 = AO_CPB + re.sub('</span>', '', ch1)
        pchapt = ch1
        if chapt2:
            ch2 = chapt2.group(0)
            ch2 = re.sub('<p class="chapterTitle level2 .*?<span>', '', ch2)
            tmp = ch1 + '【' + re.sub('</span>', '', ch2) + '】' + AO_CPE + '\r\n'
            text_page.append(tmp)
        else:
            tmp = ch1 + AO_CPE + '\r\n'
            text_page.append(tmp)
    else: # 章タイトルはないがサブタイトルがある場合
        if chapt2:
            ch2 = chapt2.group(0)
            ch2 = re.sub('<p class="chapterTitle level2 .*?<span>', '', ch2)
            tmp = pchapt + '【' + re.sub('</span>', '', ch2) + '】' + AO_CPE + '\r\n'
            text_page.append(tmp)
    if sect:
        tmp = sect.group(0)
        tmp = re.sub('<p class="widget-episodeTitle.*?">', '', tmp)
        tmp = AO_SEB + re.sub('</p>', '', tmp) + AO_SEE  + '\r\n'
        text_page.append(tmp)
    else:
        return ''
    # 本文
    text = ''
    tbody = re.search(r'<p id="p.*?</p>', body)
    while tbody:
        text = text + tbody.group(0) + '\r\n'
        body = body[tbody.end(0):]
        tbody = re.search(r'<p id="p.*?</p>', body)
    if text != '':
        text = tagfilter(text)
        text_page.append(text)
        text_page.append(AO_PB2 + '\r\n')

def loadeachpage() -> int:
    n = len(page_list)
    i = 0
    for purl in page_list:
        i += 1
        # DL開始番号が指定されていたら開始番号までスキップする
        if i < startn:
            continue
        page = loadfromhtml(purl)
        sys.stdout.write('\r各話を取得中 [ ' + str(i) + '/ ' + str(n) + ']')
        if page != '':
            text = parsepage(page)
            if text == '':
                print('')
                print(str(i)+ '話を取得出来ませんでした.')
                return -1
        # サーバー側に負担をかけないよう0.5秒の待ち時間を入れる
        time.sleep(0.5)
    if startn > 0:
        n = startn - 1
    else:
        n = 0
    print(' ... ' + str(i - n) + ' 話のエピソードを取得しました.')
    return 0

def main():
    global url, filename, startn

    if len(sys.argv) == 1:
        print('kakudlpy ver1.0 2024/12/27 (c) INOUE, masahiro')
        print('使用方法')
        print('  python kakudlpy.py [-sDL開始ページ番号] 小説トップページのURL [保存するファイル名(省略するとタイトル名で保存します)]')
        quit()
    for arg in sys.argv[1:]:
        if re.match('https://', arg):
            url = arg
        elif re.match('-s', arg):
            startn = int(arg[2:])
        else:
            filename = arg
    if not re.match(r'https://kakuyomu.jp/works/\d{19,20}', url):
        print('カクヨム作品トップページURLを指定して下さい.')
        quit()

    toppage = loadfromhtml(url)
    if toppage == '':
        print(url + ' から情報を取得出来ませんでした.')
        quit()

    if parsetoppage(toppage) == 0:
        print(str(len(page_list)) + ' 話の目次情報を取得しました.')
        if loadeachpage() == 0:
            # テキストファイルを保存する
            fout = codecs.open(filename, 'w', 'utf8')
            fout.writelines(text_page)
            fout.close()
            print(filename + ' に保存しました.')
    else:
        print('各話情報を取得出来ませんでした.')

if __name__ == '__main__':
    main()
