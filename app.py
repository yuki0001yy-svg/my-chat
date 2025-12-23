import streamlit as st
import google.generativeai as genai
import re
from youtube_transcript_api import YouTubeTranscriptApi

# ページ設定
st.set_page_config(page_title="My Private Gemini", layout="centered")

# --- ここから：パスワード認証機能 ---
def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == st.secrets["PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # パスワードを保持しない
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        st.error("😕 パスワードが違います")
        return False
    else:
        return True

if not check_password():
    st.stop()
# --- ここまで：パスワード認証機能 ---

# --- YouTube字幕取得関数 ---
def get_transcript(url):
    """YouTubeのURLから字幕を抽出する。取得できない場合はNoneを返す。"""
    try:
        # 動画IDを正規表現で抽出
        video_id_match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
        if not video_id_match:
            return None
        video_id = video_id_match.group(1)

        # 字幕リストを取得（日本語、なければ英語）
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=['ja', 'en'])
        
        # テキストを結合して返す
        full_text = " ".join([item['text'] for item in transcript_list])
        return full_text
    except Exception:
        # 字幕が無効な場合やエラー時はNoneを返す
        return None

# --- サイドバー設定 ---
st.sidebar.title("設定")
model_name = st.sidebar.selectbox(
    "モデル選択",
    ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-3-pro-preview"],
    index=2
)

# APIキーの読み込み
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
else:
    st.error("APIキーが設定されていません。StreamlitのSecretsに設定してください。")
    st.stop()

genai.configure(api_key=api_key)

if "messages" not in st.session_state:
    st.session_state.messages = []

# --- メインUI ---
st.title(f"🤖 Private Gemini ({model_name})")
st.caption("会社PC閲覧用：機密情報は入力禁止")

# ログアウトボタン
if st.sidebar.button("ログアウト"):
    st.session_state["password_correct"] = False
    st.rerun()

# 履歴の表示
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# チャット入力
if prompt := st.chat_input("ここにメッセージを入力..."):
    # 実際にモデルに送るプロンプトの初期化
    actual_prompt = prompt
    is_youtube = False

    # URL判定と字幕処理
    if prompt.startswith("https://"):
        with st.status("YouTube字幕を解析中...", expanded=False) as status:
            transcript = get_transcript(prompt)
            if transcript:
                is_youtube = True
                # 要約指示。文章を長くしても良いというあなたの要望を反映させたわ。
                actual_prompt = (
                    f"以下のYouTube動画の字幕データをもとに、重要なポイントや核心を漏らさず、"
                    f"詳細に要約してください。情報量が多くなっても構いません。\n\n"
                    f"--- 字幕データ ---\n{transcript}"
                )
                status.update(label="解析完了。要約を開始するわね。", state="complete")
            else:
                st.warning("字幕が取得できなかったわ。通常のメッセージとして処理するわ。")

    # ユーザー側のメッセージ表示
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # アシスタント側の返答生成
    with st.chat_message("assistant"):
        try:
            model = genai.GenerativeModel(model_name)
            
            # 履歴の構築（過去の巨大な字幕データを含めないよう、表示上のcontentを使用）
            chat_history = [
                {"role": m["role"], "parts": [m["content"]]} 
                for m in st.session_state.messages[:-1]
            ]
            
            chat = model.start_chat(history=chat_history)
            
            response_container = st.empty()
            full_response = ""
            
            # 処理後の actual_prompt を送信
            response = chat.send_message(actual_prompt, stream=True)
            
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    response_container.markdown(full_response)
            
            # 履歴に追加
            st.session_state.messages.append({"role": "model", "content": full_response})

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
