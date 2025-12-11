import streamlit as st
import google.generativeai as genai

# ページ設定
st.set_page_config(page_title="My Private Gemini", layout="centered")

# サイドバーでモデル選択（3.0 Proなどを指定可能に）
st.sidebar.title("設定")
model_name = st.sidebar.selectbox(
    "モデル選択",
    ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-3-pro-preview"], # 使いたいモデル名をここに追記
    index=2 # デフォルトをGemini 3.0に
)

# APIキーの読み込み（設定画面から読み込む安全な方法）
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
else:
    st.error("APIキーが設定されていません。StreamlitのSecretsに設定してください。")
    st.stop()

genai.configure(api_key=api_key)

# チャット履歴の初期化
if "messages" not in st.session_state:
    st.session_state.messages = []

# タイトル表示
st.title(f"🤖 Private Gemini ({model_name})")
st.caption("会社PC閲覧用：機密情報は入力禁止")

# 過去の履歴を表示
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 入力フォーム
if prompt := st.chat_input("ここにメッセージを入力..."):
    # ユーザーの入力を表示
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # AIの返答を生成
    with st.chat_message("assistant"):
        try:
            # モデルの準備
            model = genai.GenerativeModel(model_name)
            
            # 履歴を含めて送信（文脈を理解させる）
            chat_history = [
                {"role": m["role"], "parts": [m["content"]]} 
                for m in st.session_state.messages[:-1] # 今回の入力を除く過去ログ
            ]
            chat = model.start_chat(history=chat_history)
            
            # ストリーミング表示（文字がパラパラ出るやつ）
            response_container = st.empty()
            full_response = ""
            response = chat.send_message(prompt, stream=True)
            
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    response_container.markdown(full_response)
            
            # 履歴に保存
            st.session_state.messages.append({"role": "model", "content": full_response})

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
