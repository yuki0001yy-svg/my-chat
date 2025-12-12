import streamlit as st
import google.generativeai as genai

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
        # 初回アクセス時
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        # パスワード間違い
        st.text_input("パスワードを入力してください", type="password", on_change=password_entered, key="password")
        st.error("😕 パスワードが違います")
        return False
    else:
        # 正解
        return True

if not check_password():
    st.stop()  # パスワードが合わない限り、ここより下のコードは実行されない
# --- ここまで：パスワード認証機能 ---

# 以下、チャットアプリ本体
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

st.title(f"🤖 Private Gemini ({model_name})")
st.caption("会社PC閲覧用：機密情報は入力禁止")

# ログアウトボタン（簡易版）
if st.sidebar.button("ログアウト"):
    st.session_state["password_correct"] = False
    st.rerun()

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("ここにメッセージを入力..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            model = genai.GenerativeModel(model_name)
            chat_history = [
                {"role": m["role"], "parts": [m["content"]]} 
                for m in st.session_state.messages[:-1]
            ]
            chat = model.start_chat(history=chat_history)
            
            response_container = st.empty()
            full_response = ""
            response = chat.send_message(prompt, stream=True)
            
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    response_container.markdown(full_response)
            
            st.session_state.messages.append({"role": "model", "content": full_response})

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
