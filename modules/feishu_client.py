"""
飞书统一客户端 SDK
覆盖：Token 管理 / 多维表格(Bitable) / 文档(Docs) / 消息(Message)
"""
import time
import threading
import requests

BASE = "https://open.feishu.cn/open-apis"


class FeishuError(Exception):
    def __init__(self, code: int, msg: str):
        super().__init__(f"[{code}] {msg}")
        self.code = code


class FeishuClient:
    """线程安全的飞书 API 客户端，token 自动刷新。"""

    def __init__(self, app_id: str = "", app_secret: str = ""):
        self._app_id = app_id
        self._app_secret = app_secret
        self._token = ""
        self._expiry = 0.0
        self._lock = threading.Lock()

    def configure(self, app_id: str, app_secret: str):
        with self._lock:
            if app_id != self._app_id or app_secret != self._app_secret:
                self._app_id = app_id
                self._app_secret = app_secret
                self._token = ""
                self._expiry = 0.0

    # ── Token ────────────────────────────────────────────────────────────────

    def token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._expiry - 60:
                return self._token
            resp = requests.post(
                f"{BASE}/auth/v3/tenant_access_token/internal",
                json={"app_id": self._app_id, "app_secret": self._app_secret},
                timeout=10,
            )
            data = self._check(resp)
            self._token = data["tenant_access_token"]
            self._expiry = time.time() + data.get("expire", 7200)
            return self._token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token()}", "Content-Type": "application/json"}

    def _check(self, resp: requests.Response) -> dict:
        resp.raise_for_status()
        body = resp.json()
        code = body.get("code", -1)
        if code != 0:
            raise FeishuError(code, body.get("msg", "unknown error"))
        return body.get("data", body)

    # ── 多维表格 (Bitable) ───────────────────────────────────────────────────

    def bitable_list(self, app_token: str, table_id: str, page_size: int = 100) -> list[dict]:
        """拉取表格全部记录（自动翻页）。"""
        url = f"{BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        params: dict = {"page_size": page_size}
        records = []
        while True:
            data = self._check(requests.get(url, headers=self._headers(), params=params, timeout=10))
            records.extend(data.get("items", []))
            if not data.get("has_more") or not data.get("page_token"):
                break
            params["page_token"] = data["page_token"]
        return records

    def bitable_get(self, app_token: str, table_id: str, record_id: str) -> dict:
        """获取单条记录。"""
        url = f"{BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        return self._check(requests.get(url, headers=self._headers(), timeout=10)).get("record", {})

    def bitable_add(self, app_token: str, table_id: str, fields: dict) -> str:
        """新增一条记录，返回 record_id。"""
        url = f"{BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records"
        data = self._check(requests.post(url, headers=self._headers(), json={"fields": fields}, timeout=10))
        return data.get("record", {}).get("record_id", "")

    def bitable_update(self, app_token: str, table_id: str, record_id: str, fields: dict) -> bool:
        """更新一条记录。"""
        url = f"{BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        self._check(requests.put(url, headers=self._headers(), json={"fields": fields}, timeout=10))
        return True

    def bitable_delete(self, app_token: str, table_id: str, record_id: str) -> bool:
        """删除一条记录。"""
        url = f"{BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records/{record_id}"
        self._check(requests.delete(url, headers=self._headers(), timeout=10))
        return True

    def bitable_batch_add(self, app_token: str, table_id: str, records: list[dict]) -> list[str]:
        """批量新增，records 是 fields dict 的列表，返回 record_id 列表。"""
        url = f"{BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create"
        payload = {"records": [{"fields": f} for f in records]}
        data = self._check(requests.post(url, headers=self._headers(), json=payload, timeout=15))
        return [r.get("record_id", "") for r in data.get("records", [])]

    def bitable_batch_update(self, app_token: str, table_id: str, updates: list[dict]) -> bool:
        """批量更新，updates 格式：[{"record_id": ..., "fields": {...}}, ...]"""
        url = f"{BASE}/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_update"
        payload = {"records": updates}
        self._check(requests.put(url, headers=self._headers(), json=payload, timeout=15))
        return True

    def bitable_list_tables(self, app_token: str) -> list[dict]:
        """列出多维表格下所有 sheet/table。"""
        url = f"{BASE}/bitable/v1/apps/{app_token}/tables"
        data = self._check(requests.get(url, headers=self._headers(), timeout=10))
        return data.get("items", [])

    # ── 文档 (Docs) ──────────────────────────────────────────────────────────

    def doc_get_content(self, document_id: str) -> dict:
        """获取文档全文内容（返回原始 document 结构）。"""
        url = f"{BASE}/docx/v1/documents/{document_id}/raw_content"
        return self._check(requests.get(url, headers=self._headers(), timeout=15))

    def doc_get_blocks(self, document_id: str) -> list[dict]:
        """获取文档所有 Block（结构化内容）。"""
        url = f"{BASE}/docx/v1/documents/{document_id}/blocks"
        params: dict = {"page_size": 500}
        blocks = []
        while True:
            data = self._check(requests.get(url, headers=self._headers(), params=params, timeout=15))
            blocks.extend(data.get("items", []))
            if not data.get("has_more") or not data.get("page_token"):
                break
            params["page_token"] = data["page_token"]
        return blocks

    def doc_create(self, title: str, folder_token: str = "") -> dict:
        """新建文档，返回 {document_id, url}。"""
        url = f"{BASE}/docx/v1/documents"
        payload: dict = {"title": title}
        if folder_token:
            payload["folder_token"] = folder_token
        data = self._check(requests.post(url, headers=self._headers(), json=payload, timeout=10))
        doc = data.get("document", data)
        return {"document_id": doc.get("document_id", ""), "url": doc.get("url", "")}

    def doc_append_text(self, document_id: str, text: str) -> bool:
        """在文档末尾追加一段纯文本（paragraph block）。"""
        url = f"{BASE}/docx/v1/documents/{document_id}/blocks/batch_update"
        block = {
            "block_type": 2,  # paragraph
            "paragraph": {
                "elements": [{"type": 0, "text_run": {"content": text}}]
            },
        }
        # 先获取末尾 block index
        blocks = self.doc_get_blocks(document_id)
        parent_id = blocks[0].get("block_id", document_id) if blocks else document_id
        insert_url = f"{BASE}/docx/v1/documents/{document_id}/blocks/{parent_id}/children"
        payload = {"children": [block], "index": -1}
        self._check(requests.post(insert_url, headers=self._headers(), json=payload, timeout=10))
        return True

    # ── 消息 (Message) ───────────────────────────────────────────────────────

    def msg_send_text(self, receive_id: str, text: str, id_type: str = "open_id") -> str:
        """发送纯文本消息，返回 message_id。id_type: open_id / user_id / email / chat_id"""
        return self._send_msg(receive_id, id_type, "text", {"text": text})

    def msg_send_markdown(self, receive_id: str, markdown: str, id_type: str = "open_id") -> str:
        """发送富文本（markdown）消息。"""
        content = {"zh_cn": {"content": [[{"tag": "md", "text": markdown}]]}}
        return self._send_msg(receive_id, id_type, "post", content)

    def msg_send_card(self, receive_id: str, card: dict, id_type: str = "open_id") -> str:
        """发送卡片消息，card 为飞书卡片 JSON 结构。"""
        return self._send_msg(receive_id, id_type, "interactive", card)

    def msg_send_to_chat(self, chat_id: str, text: str) -> str:
        """发送文本消息到群。"""
        return self.msg_send_text(chat_id, text, id_type="chat_id")

    def msg_reply(self, message_id: str, text: str) -> str:
        """回复某条消息。"""
        url = f"{BASE}/im/v1/messages/{message_id}/reply"
        import json as _json
        payload = {"msg_type": "text", "content": _json.dumps({"text": text})}
        data = self._check(requests.post(url, headers=self._headers(), json=payload, timeout=10))
        return data.get("message_id", "")

    def msg_get(self, message_id: str) -> dict:
        """获取消息详情。"""
        url = f"{BASE}/im/v1/messages/{message_id}"
        data = self._check(requests.get(url, headers=self._headers(), timeout=10))
        items = data.get("items", [])
        return items[0] if items else {}

    def _send_msg(self, receive_id: str, id_type: str, msg_type: str, content) -> str:
        import json as _json
        url = f"{BASE}/im/v1/messages?receive_id_type={id_type}"
        payload = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": _json.dumps(content) if not isinstance(content, str) else content,
        }
        data = self._check(requests.post(url, headers=self._headers(), json=payload, timeout=10))
        return data.get("message_id", "")

    # ── 用户 ─────────────────────────────────────────────────────────────────

    def user_get_by_email(self, email: str) -> dict:
        """通过邮箱查 open_id / user_id。"""
        url = f"{BASE}/contact/v3/users/batch_get_id?user_id_type=open_id"
        data = self._check(requests.post(url, headers=self._headers(),
                                         json={"emails": [email]}, timeout=10))
        results = data.get("user_list", [])
        return results[0] if results else {}

    def user_get_me(self) -> dict:
        """获取当前 bot 所属应用信息。"""
        url = f"{BASE}/contact/v3/scopes"
        return self._check(requests.get(url, headers=self._headers(), timeout=10))
