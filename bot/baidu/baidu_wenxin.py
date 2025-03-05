# encoding:utf-8
import base64
import io
import requests
import json
from common import const
from bot.bot import Bot
from bot.session_manager import SessionManager
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from config import conf
from bot.baidu.baidu_wenxin_session import BaiduWenxinSession

BAIDU_API_KEY = conf().get("baidu_wenxin_api_key")
BAIDU_SECRET_KEY = conf().get("baidu_wenxin_secret_key")

class BaiduWenxinBot(Bot):

    def __init__(self):
        super().__init__()
        wenxin_model = conf().get("baidu_wenxin_model")
        self.prompt_enabled = conf().get("baidu_wenxin_prompt_enabled")
        if self.prompt_enabled:
            self.prompt = conf().get("character_desc", "")
            if self.prompt == "":
                logger.warn("[BAIDU] Although you enabled model prompt, character_desc is not specified.")
        if wenxin_model is not None:
            wenxin_model = conf().get("baidu_wenxin_model") or "eb-instant"
        else:
            if conf().get("model") and conf().get("model") == const.WEN_XIN:
                wenxin_model = "completions"
            elif conf().get("model") and conf().get("model") == const.WEN_XIN_4:
                wenxin_model = "completions_pro"

        self.sessions = SessionManager(BaiduWenxinSession, model=wenxin_model)

    def reply(self, query, context=None):
        # acquire reply content
        if context and context.type:
            if context.type == ContextType.TEXT:
                logger.info("[BAIDU] query={}".format(query))
                session_id = context["session_id"]
                reply = None
                if query == "#清除记忆":
                    self.sessions.clear_session(session_id)
                    reply = Reply(ReplyType.INFO, "记忆已清除")
                elif query == "#清除所有":
                    self.sessions.clear_all_session()
                    reply = Reply(ReplyType.INFO, "所有人记忆已清除")
                else:
                    session = self.sessions.session_query(query, session_id)
                    result = self.reply_text(session)
                    total_tokens, completion_tokens, reply_content = (
                        result["total_tokens"],
                        result["completion_tokens"],
                        result["content"],
                    )
                    logger.debug(
                        "[BAIDU] new_query={}, session_id={}, reply_cont={}, completion_tokens={}".format(session.messages, session_id, reply_content, completion_tokens)
                    )

                    if total_tokens == 0:
                        reply = Reply(ReplyType.ERROR, reply_content)
                    else:
                        self.sessions.session_reply(reply_content, session_id, total_tokens)
                        reply = Reply(ReplyType.TEXT, reply_content)
                return reply
            elif context.type == ContextType.IMAGE_CREATE:
                if not conf().get("text_to_image"):
                    logger.warn("[LinkAI] text_to_image is not enabled, ignore the IMAGE_CREATE request")
                    return Reply(ReplyType.TEXT, "")
                ok, retstring = self.create_img(query, 0)
                reply = None
                if ok:
                    reply = Reply(ReplyType.IMAGE_URL, retstring)
                else:
                    reply = Reply(ReplyType.ERROR, retstring)
                return reply

    def reply_text(self, session: BaiduWenxinSession, retry_count=0):
        try:
            logger.info("[BAIDU] model={}".format(session.model))
            access_token = self.get_access_token()
            if access_token == 'None':
                logger.warn("[BAIDU] access token 获取失败")
                return {
                    "total_tokens": 0,
                    "completion_tokens": 0,
                    "content": 0,
                }
            url = "https://qianfan.baidubce.com/v2/chat/completions"
            headers = {
                'Content-Type': 'application/json',
                'Authorization':'Bearer '+conf().get("baidu_wenxin_api_key")

            }
            payload = {'messages': session.messages, 'system': self.prompt,"model": session.model} if self.prompt_enabled else {'messages': session.messages,"model": session.model}
            response = requests.request("POST", url, headers=headers, data=json.dumps(payload))
            response_text = json.loads(response.text)
            logger.info(f"[BAIDU] response text={response_text}")
            res_content = response_text["choices"][0]["message"]["content"]
            total_tokens = response_text["usage"]["total_tokens"]
            completion_tokens = response_text["usage"]["completion_tokens"]
            logger.info("[BAIDU] reply={}".format(res_content))
            return {
                "total_tokens": total_tokens,
                "completion_tokens": completion_tokens,
                "content": res_content,
            }
        except Exception as e:
            need_retry = retry_count < 2
            logger.warn("[BAIDU] Exception: {}".format(e))
            need_retry = False
            self.sessions.clear_session(session.session_id)
            result = {"total_tokens": 0, "completion_tokens": 0, "content": "出错了: {}".format(e)}
            return result



    def create_img(self, query, retry_count=0, api_key=None):
        try:
            logger.info("[BAIDU] image_query={}".format(query))

            url = "https://qianfan.baidubce.com/v2/images/generations"
            headers = {
                "Content-Type": "application/json",
                'Authorization':'Bearer '+conf().get("baidu_wenxin_api_key")
            }
            data = {
                "prompt": query,
                "model": "irag-1.0",
            }
            res = requests.post(url, headers=headers, json=data, timeout=(5, 90))
            image_url = res.json()["data"][0]["url"]
            # 转换过程


            logger.info("[OPEN_AI] image_url={}".image_url)

            return True, image_url
        except Exception as e:
            logger.error(format(e))
            return False, "画图出现问题，请休息一下再问我吧"
