import streamlit as st
from google import genai
from google.genai import types
import re

# --- 定数 ---
DEFAULT_MODEL_INDEX = 0
MODEL_OPTIONS = [
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
]
URL_PATTERN = re.compile(r"https?://\S+")

# --- ページ設定 ---
st.set_page_config(page_title="My Private Gemini", layout="centered")

# --- CSS注入: チャット内Markdownの見た目を調整 ---
st.markdown(
    """
<style>
/* 見出しサイズを抑え、余白を詰める */
[data-testid="stChatMessage"] h1 {
    font-size: 1.4rem !important;
    margin-top: 0.6rem !important;
    margin-bottom: 0.4rem !important;
    font-weight: 600 !important;
}
[data-testid="stChatMessage"] h2 {
    font-size: 1.2rem !important;
    margin-top: 0.5rem !important;
    margin-bottom: 0.3rem !important;
    font-weight: 600 !important;
}
[data-testid="stChatMessage"] h3 {
    font-size: 1.08rem !important;
    margin-top: 0.4rem !important;
    margin-bottom: 0.3rem !important;
    font-weight: 600 !important;
}
[data-testid="stChatMessage"] h4,
[data-testid="stChatMessage"] h5,
[data-testid="stChatMessage"] h6 {
    font-size: 1rem !important;
    margin-top: 0.3rem !important;
    margin-bottom: 0.2rem !important;
    font-weight: 600 !important;
}
/* 段落・リスト・引用の余白と行間 */
[data-testid="stChatMessage"] p {
    margin-bottom: 0.4rem !important;
    line-height: 1.6 !important;
}
[data-testid="stChatMessage"] ul,
[data-testid="stChatMessage"] ol {
    margin-top: 0.2rem !important;
    margin-bottom: 0.4rem !important;
    padding-left: 1.5rem !important;
}
[data-testid="stChatMessage"] li {
    margin-bottom: 0.15rem !important;
    line-height: 1.5 !important;
}
[data-testid="stChatMessage"] blockquote {
    margin: 0.4rem 0 !important;
    padding: 0.3rem 0.8rem !important;
    border-left: 3px solid #ccc !important;
    color: #555 !important;
}
[data-testid="stChatMessage"] table {
    margin: 0.4rem 0 !important;
    font-size: 0.9rem !important;
}
</style>
""",
    unsafe_allow_html=True,
)


# --- パスワード認証 ---
def check_password():
    """パスワードが正しければ True を返す"""

    def password_entered():
        if st.session_state["password"] == st.secrets["PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input(
            "パスワードを入力してください",
            type="password",
            on_change=password_entered,
            key="password",
        )
        return False
    elif not st.session_state["password_correct"]:
        st.text_input(
            "パスワードを入力してください",
            type="password",
            on_change=password_entered,
            key="password",
        )
        st.error("パスワードが違います")
        return False
    else:
        return True


if not check_password():
    st.stop()


# --- ヘルパー関数 ---
def build_tools_config(grounding_on, url_context_on, has_urls):
    """サイドバー設定に基づいてツールリストを構築する"""
    tools = []
    if grounding_on:
        tools.append(types.Tool(google_search=types.GoogleSearch()))
    if url_context_on and has_urls:
        tools.append(types.Tool(url_context=types.UrlContext()))
    return tools if tools else None


def build_api_contents(api_history, current_prompt):
    """API送信用のcontentsリストを構築する（過去履歴 + 現在のユーザー入力）"""
    contents = []
    for entry in api_history:
        contents.append(
            types.Content(
                role=entry["role"],
                parts=[types.Part(text=entry["content"])],
            )
        )
    contents.append(
        types.Content(role="user", parts=[types.Part(text=current_prompt)])
    )
    return contents


def extract_grounding_metadata(last_chunk):
    """最終チャンクからグラウンディングメタデータを安全に抽出する"""
    if last_chunk is None:
        return None
    try:
        candidates = getattr(last_chunk, "candidates", None)
        if not candidates:
            return None
        gm = getattr(candidates[0], "grounding_metadata", None)
        if gm is None:
            return None

        metadata = {"search_queries": [], "sources": []}

        queries = getattr(gm, "web_search_queries", None)
        if queries:
            metadata["search_queries"] = list(queries)

        chunks = getattr(gm, "grounding_chunks", None)
        if chunks:
            for c in chunks:
                web = getattr(c, "web", None)
                if web:
                    metadata["sources"].append(
                        {
                            "uri": getattr(web, "uri", ""),
                            "title": getattr(web, "title", ""),
                        }
                    )

        if not metadata["search_queries"] and not metadata["sources"]:
            return None
        return metadata
    except Exception:
        return None


def render_citation_panel(metadata):
    """引用元パネルを折りたたみ表示する"""
    if not metadata:
        return
    with st.expander("引用元情報", expanded=False):
        if metadata.get("search_queries"):
            st.markdown("**検索クエリ:**")
            for q in metadata["search_queries"]:
                st.markdown(f"- `{q}`")
        if metadata.get("sources"):
            st.markdown("**参照元:**")
            for src in metadata["sources"]:
                title = src.get("title", "")
                uri = src.get("uri", "")
                if uri and title:
                    st.markdown(f"- [{title}]({uri})")
                elif uri:
                    st.markdown(f"- [{uri}]({uri})")
                elif title:
                    st.markdown(f"- {title}")


# --- セッションステート初期化 ---
# 表示用履歴（画面に表示するメッセージ）
if "display_messages" not in st.session_state:
    st.session_state.display_messages = []
# API送信用履歴（Gemini APIに送るコンテキスト）
if "api_history" not in st.session_state:
    st.session_state.api_history = []

# --- サイドバー ---
st.sidebar.title("設定")

model_name = st.sidebar.selectbox(
    "モデル選択", MODEL_OPTIONS, index=DEFAULT_MODEL_INDEX
)

grounding_enabled = st.sidebar.toggle(
    "Google検索グラウンディング",
    value=False,
    help="Googleの検索結果を参照して回答を生成します",
)

url_context_enabled = st.sidebar.toggle(
    "URLコンテキスト",
    value=False,
    help="メッセージ内のURLの内容を参照して回答を生成します",
)

st.sidebar.divider()

if st.sidebar.button("チャットをクリア"):
    st.session_state.display_messages = []
    st.session_state.api_history = []
    st.rerun()

if st.sidebar.button("ログアウト"):
    st.session_state["password_correct"] = False
    st.rerun()

# --- APIクライアント初期化 ---
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
else:
    st.error("APIキーが設定されていません。StreamlitのSecretsに設定してください。")
    st.stop()

client = genai.Client(api_key=api_key)

# --- メインUI ---
st.title("Private Gemini")
st.caption(f"モデル: {model_name} | 会社PC閲覧用：機密情報は入力禁止")

# --- 履歴表示 ---
for msg in st.session_state.display_messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and msg.get("grounding_metadata"):
            render_citation_panel(msg["grounding_metadata"])

# --- チャット入力 & レスポンス生成 ---
if prompt := st.chat_input("ここにメッセージを入力..."):
    # URL有無判定
    has_urls = bool(URL_PATTERN.search(prompt))

    # ツール設定構築
    tools = build_tools_config(grounding_enabled, url_context_enabled, has_urls)

    # 表示用履歴にユーザーメッセージ追加
    st.session_state.display_messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # API用contents構築（過去履歴 + 今回のプロンプト）
    contents = build_api_contents(st.session_state.api_history, prompt)
    config = types.GenerateContentConfig(tools=tools) if tools else None

    # アシスタント応答生成
    with st.chat_message("assistant"):
        try:
            response_container = st.empty()
            full_response = ""
            last_chunk = None

            response_stream = client.models.generate_content_stream(
                model=model_name,
                contents=contents,
                config=config,
            )

            for chunk in response_stream:
                chunk_text = ""
                try:
                    chunk_text = chunk.text or ""
                except (ValueError, AttributeError):
                    pass

                if chunk_text:
                    full_response += chunk_text
                    response_container.markdown(full_response)

                last_chunk = chunk

            # グラウンディングメタデータ抽出
            grounding_meta = extract_grounding_metadata(last_chunk)
            if grounding_meta:
                render_citation_panel(grounding_meta)

            # 表示用履歴にアシスタント回答追加
            st.session_state.display_messages.append(
                {
                    "role": "assistant",
                    "content": full_response,
                    "grounding_metadata": grounding_meta,
                }
            )

            # API送信用履歴に追加（roleはGemini APIの規約に合わせる）
            st.session_state.api_history.append(
                {"role": "user", "content": prompt}
            )
            st.session_state.api_history.append(
                {"role": "model", "content": full_response}
            )

        except Exception as e:
            error_msg = str(e).lower()
            if grounding_enabled and (
                "grounding" in error_msg or "google_search" in error_msg
            ):
                st.error(
                    f"選択中のモデル `{model_name}` では Grounding with Google Search を"
                    f"使用できません。モデルまたは設定を確認してください。\n\n"
                    f"エラー詳細: {e}"
                )
            else:
                st.error(f"エラーが発生しました: {e}")
