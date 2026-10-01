# -*- coding: utf-8 -*-
"""线协议：4B 大端长度前缀 + UTF-8 JSON 头 + 二进制体。

帧格式（加密层之下，crypto.py 会整体再加密）：
    [4B uint32 header_len][JSON header(含 body_len)][body 二进制]

防护：header/body 超限、坏 JSON 一律视为协议错误（由调用方断连）。
"""
import json
import struct
from enum import Enum

from config import CFG


class MsgType(str, Enum):
    # 连接与元
    HELLO = "hello"
    SET_PWD = "set_pwd"    # R47：昵称密码设置/修改/清除（header: old/new；new 空=清除）
    WELCOME = "welcome"
    ROSTER = "roster"
    SYSTEM = "system"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"
    BLOCK_SET = "block_set"        # R50：设置/取消屏蔽（header: target, on；服务器按 uid 持久化）
    BLOCK_LIST = "block_list"      # R50：请求我的屏蔽名单（服务器回 BLOCK_LIST 帧）
    # R51 服务器权威定时消息（客户端离线也会到点发出；队列持久化）
    SCHED_SET = "sched_set"        # 创建定时消息（header: channel/to/text/fire_at；服务器回 SCHED_LIST）
    SCHED_LIST = "sched_list"      # 拉取我的待发列表（服务器回 SCHED_LIST 帧带 items=[{rid,channel,to,text,fire_at,created}]）
    SCHED_CANCEL = "sched_cancel"  # 取消定时消息（header: rid；服务器回 SCHED_LIST）
    # 聊天
    # CHAT 帧可选字段：mentions=[uid] R14 单成员 @提及；everyone=True R6 群内 @全体
    # /@全员/@所有人 广播（仅普通群聊，不用于 E2EE/私密频道）。新客户端缺失这些
    # 标记时按普通群消息处理，不影响旧版兼容。
    # R71 新增可选字段：
    #   card={uid,nick}   联系人名片（服务器白名单化后透传，接受端渲染成可点卡片；
    #                     头像不随帧下发，接收端按 uid 走 AVATAR_GET）。
    #   thread_root       语义放开：channel 频道（kind="channel"）内非创建者也可带
    #                     thread_root 回帖；不带则该频道仍只读（仅创建者可发贴）。
    CHAT = "chat"
    TYPING = "typing"  # 正在输入指示（header 带 channel/to；服务器广播给频道应收方，3s 过期）
    NUDGE = "nudge"    # R67 拍一拍（header 带 channel/to/target/target_nick；服务器广播给频道应收方，5s/人限速，不入历史）
    SHAKE = "shake"    # R68 窗口抖动（header 带 channel/to；服务器广播给频道应收方，10s/人限速，不入历史/审计）
    VOICE = "voice"    # 语音消息：header 带 channel/to/duration，body=WAV（服务端透传）
    MSG_EDIT = "edit"      # 编辑消息（改文本）
    MSG_DEL = "del"        # 撤回/删除消息（header: seq；scope=self 仅本人/both 双方可删私聊）
    REACTION = "reaction"  # 表情回应（对 seq 消息加/摘 emoji；msg["reactions"]={emoji:{uid:ts}}）
    READ = "read"          # 已读回执（阅读到 seq；read 事件带 key/uid/seq）
    READ_DETAIL = "read_detail"  # R33③：已读详情（请求 header: key；回帧 header: key/readers=[{uid,nick,seq}]）
    MSG_READERS = "msg_readers"  # C9②：群@已读 by N 逐人统计（请求 header: key=group:{gid}/seq；回帧 members/unread/count/total）
    PIN = "pin"            # 消息置顶（on=True 置顶/False 取消；pin 事件带 key/msg 快照）
    PURGE = "purge"        # 会话清理（until_seq 之前消息作废；purge 事件带 key/until_seq）
    DRAFT_SET = "draft_set"    # R29B：草稿同步（channel/to/text；服务器按 uid 内存存，welcome 带回）
    # R34 群内话题 Threads
    THREAD_FETCH = "thread_fetch"        # 拉取话题回复（header: channel/to/root_seq）
    THREAD_HISTORY = "thread_history"    # 话题回复回帧（header: channel/to/root_seq，msgs=该话题全部回复）
    # R35 生态包：贴纸商店
    STICKER_SHOP = "sticker_shop"        # 拉商店目录（服务器回 STICKER_SHOP_LIST）
    STICKER_SHOP_LIST = "sticker_shop_list"   # 商店目录回帧（packs+当前订阅）
    STICKER_SUB = "sticker_sub"          # 订阅/退订包 {pack_id, on}（回帧带全量订阅）
    # R36 E2EE 密聊（服务器纯透传，不解析不存储正文）
    E2EE_PUB = "e2ee_pub"            # 1v1 握手：发身份公钥（header: to/pub/nonce；服务器单播转发）
    E2EE_PUB_ACK = "e2ee_pub_ack"    # 握手应答：回身份公钥（header: to/pub/nonce 原样带回）
    E2EE_CHAT = "e2ee_chat"          # 1v1 密聊：body=AES-GCM(JSON)（header: to；不进服务器历史）
    E2EE_GROUP = "e2ee_group"        # 群密聊：body=AES-GCM(sender_key)（header: gid/epoch/from）
    E2EE_SK_DIST = "e2ee_sk_dist"    # sender key 分发：envelopes=[{to,ct}]（服务器逐个单播）
    E2EE_SK_DIST_ONE = "e2ee_sk_dist_one"  # 服务器拆包后的单个信封（header: gid/epoch/from）
    E2EE_SK_REQ = "e2ee_sk_req"      # 离线成员上线补发请求（header: gid/from）→ 群内广播
    # R38 1v1 语音对讲（信令走 TCP，音频 UDP 直连；服务器仅搭桥，不见音频字节）
    CALL_RING = "call_ring"          # 主叫发起（header: to/from/nick；服务器校验在线转发）
    CALL_ACCEPT = "call_accept"      # 被叫接受（header: to/from）
    CALL_REJECT = "call_reject"      # 被叫拒绝（header: to/from/reason）
    CALL_READY = "call_ready"        # 主叫上报 UDP 端口（header: to/port；服务器回填 ip 转发）
    CALL_END = "call_end"            # 挂断/失败（header: to/reason；双向转发）
    # R72 多人语音房（全互联 mesh：服务器只发名册/地址，音频 UDP 直连不经服务器）
    ROOM_JOIN = "room_join"          # 入房（header: room；room="public" 或 "group:<gid>"）
    ROOM_LEAVE = "room_leave"        # 退房（header: room）
    ROOM_ADDR = "room_addr"          # 上报本机 UDP 端口（header: room/port）→ 服务器回填 ip 广播
    ROOM_STATE = "room_state"        # 服务器广播名册（header: room/count/members=[{uid,nick}]）
    ROOM_PEERS = "room_peers"        # 单播给新入房者：已在房者全量地址（peers=[{uid,ip,port}]）
    # R72 位置共享（geo 随 CHAT 透传；实时共享走 GEO_LIVE 定时重发，不入历史）
    GEO_LIVE = "geo_live"            # 实时位置刷新（header: channel/to/geo={...}；广播不入历史）
    GEO_STOP = "geo_stop"            # 停止共享（header: channel/to/session；广播让对端摘除标记）
    # R72 圆形视频留言（body=VMA1 容器字节；服务器内存短留，TTL 同语音消息）
    VMEMO = "vmemo"                  # 视频留言（header: channel/to/duration；body=VMA1）
    # R26 投票 / 链接预览
    POLL = "poll"              # 发起投票（header 带 channel/to/question/options
    #                            + R70C：anonymous/multi/quiz/correct；服务器聚合票数）
    POLL_VOTE = "poll_vote"    # 投票（seq/option；多选=再点取消；服务器广播 poll_state）
    POLL_STATE = "poll_state"  # 服务器广播：R70C 形状 {seq,counts,total,end,mine?,correct?}
    #                            （非匿名另带 votes:{uid:[idx..]}；匿名只广播计数+按人单播 mine）
    PREVIEW = "preview"        # 链接预览补发：{seq, preview:{title,url,image,desc,domain}}
    # 历史与表情包
    HISTORY = "history"
    # R37 加密云历史（服务器只存密文 blob，按 uid 一份，重启保留）
    CLOUD_PUT = "cloud_put"      # 上传：body=AES-GCM(salt+nonce+ct)（header: size/ts）
    CLOUD_DONE = "cloud_done"    # 上传回执（header: size/ts；失败走 error 帧 code=cloud）
    CLOUD_GET = "cloud_get"      # 拉取 → 服务器回 CLOUD_DATA（无备份时 size=0）
    CLOUD_DATA = "cloud_data"    # 回帧：body=blob（header: size/ts；size=0 表示云端无备份）
    STICKER_LIST = "sticker_list"
    STICKER_CUSTOM_ADD = "sticker_custom_add"    # R30C：上传自定义贴纸（header: code/label/ext，body=图片字节）
    STICKER_CUSTOM_DEL = "sticker_custom_del"    # R30C：删除自定义贴纸（header: code）
    STICKER_CUSTOM_GET = "sticker_custom_get"    # R30C：拉取贴纸图片（header: code）
    STICKER_CUSTOM_DATA = "sticker_custom_data"  # R30C：服务器回图片（header: code/ext，body=字节）
    # R64 贴纸包深化：包管理 / 包导航 / 包封面 / 包内排序
    STICKER_PACK_RENAME = "sticker_pack_rename"  # 重命名自定义包（header: old/new）
    STICKER_PACK_DEL = "sticker_pack_del"        # 删除自定义包（header: pack；连包内贴纸一并删）
    STICKER_PACK_COVER = "sticker_pack_cover"    # 设/清包封面（header: pack/ext，body=图片；无 body→清除）
    STICKER_PACK_COVER_GET = "sticker_pack_cover_get"    # 拉取包封面（header: pack）
    STICKER_PACK_COVER_DATA = "sticker_pack_cover_data"  # 服务器回包封面（header: pack/ext，body=字节）
    STICKER_REORDER = "sticker_reorder"          # 包内排序（header: code/dir=up|down|top|bottom）
    # 群聊
    GROUP_LIST = "group_list"
    GROUP_CREATE = "group_create"
    GROUP_JOIN = "group_join"
    GROUP_LEAVE = "group_leave"
    GROUP_STATE = "group_state"
    GROUP_KICK = "group_kick"                    # 踢人（群主/管理员）
    GROUP_MUTE = "group_mute"                    # 禁言/解禁（duration<=0 解禁）
    GROUP_SLOW = "group_slow"                    # R70D：群慢速模式（header: gid/seconds，0=关闭）
    GROUP_SET_ADMIN = "group_set_admin"          # 设/撤管理员（仅群主）
    GROUP_ANNOUNCE = "group_announce"            # 群公告（群主/管理员设置，空=NULL清除）
    GROUP_ANN_MODE = "group_ann_mode"            # C9①：仅公告说话模式开关（群主/管理员；header gid/on）
    GROUP_INVITE_GET = "group_invite_get"        # R28：群主/管理员获取群邀请码（header: gid）
    GROUP_INVITE = "group_invite"                # R28：服务器单播回邀请码（header: gid/code）
    GROUP_JOIN_INVITE = "group_join_invite"      # R28：凭邀请码入群（header: code）
    GROUP_RENAME = "group_rename"                # R28：群改名（header: gid/name，群主/管理员）
    GROUP_ABOUT = "group_about"                  # R9H：群简介（header: gid/about ≤80字，群主/管理员）
    GROUP_AVATAR_SET = "group_avatar_set"        # R9H：群头像上传（header: gid/ext；body=图片字节）
    GROUP_AVATAR_DEL = "group_avatar_del"        # R9H：清空群头像（header: gid → 服务器回 GROUP_AVATAR_DATA ext=""）
    GROUP_AVATAR_GET = "group_avatar_get"        # R9H：拉取群头像（header: gid → 服务器单播 GROUP_AVATAR_DATA）
    GROUP_AVATAR_DATA = "group_avatar_data"      # R9H：群头像回帧（header: gid/ext；body=字节；ext=""=无）
    # 文件传输
    FILE_OFFER = "file_offer"
    FILE_ACCEPT = "file_accept"
    FILE_REJECT = "file_reject"
    FILE_LISTEN = "file_listen"      # 发送方上报直连监听端口
    FILE_DIRECT = "file_direct"      # 服务器把直连地址发给接收方
    FILE_DIRECT_OK = "file_direct_ok"  # 直连建立成功（服务器停用中转）
    FILE_DATA = "file_data"
    FILE_CHUNK_ACK = "file_chunk_ack"
    FILE_DONE = "file_done"
    FILE_VERIFY = "file_verify"
    FILE_PROGRESS = "file_progress"
    FILE_CANCEL = "file_cancel"
    # 群文件库（与 1v1 文件传输 FileManager/文件帧路径解耦，自成一体）
    GROUP_FILE_LIST = "group_file_list"            # 请求群文件列表（header: gid → 服务器回 GROUP_FILE_LIST_RES）
    GROUP_FILE_LIST_RES = "group_file_list_res"    # 回帧（header: gid；body=JSON 数组 [{fid,name,size,ts,uid,nick}]）
    GROUP_FILE_UPLOAD_START = "group_file_upload_start"  # 上传起始（header: gid/name/size → 服务器分配 fid 回 INFO）
    GROUP_FILE_UPLOAD_INFO = "group_file_upload_info"    # 服务器回 fid（header: gid/fid/off，用于续传起点）
    GROUP_FILE_UPLOAD = "group_file_upload"        # 上传数据块（header: gid/fid/off；body=块字节 ≤64KB）
    GROUP_FILE_UPLOAD_DONE = "group_file_upload_done"   # 上传收尾（header: gid/fid/off=总字节 → 归整、广播）
    GROUP_FILE_DEL = "group_file_del"              # 删除群文件（header: gid/fid；本人/owner/admin 可删）
    GROUP_FILE_GET = "group_file_get"              # 下载（header: gid/fid → 服务器逐块回 GROUP_FILE_DATA）
    GROUP_FILE_DATA = "group_file_data"            # 下载数据块（header: gid/fid/off/more（0=结束）；body=块字节）
    GROUP_FILE_NOTIFY = "group_file_notify"        # 群内广播：文件增删（header: gid/text；老客户端按普通广播忽略）
    # 游戏
    GAME_LIST = "game_list"
    GAME_CREATE = "game_create"
    GAME_JOIN = "game_join"
    GAME_LEAVE = "game_leave"
    GAME_SPECTATE = "game_spectate"
    GAME_START = "game_start"
    GAME_STATE = "game_state"
    GAME_PRIVATE = "game_private"
    GAME_ACTION = "game_action"
    GAME_SYNC = "game_sync"        # R49：重进/刷新后补拉房间状态
    GAME_RESULT = "game_result"
    GAME_ERROR = "game_error"
    # R70H 摸鱼排行榜（opt-in，服务器默认关闭；按游戏名持久化累计积分）
    FISH_SCORE = "fish_score"      # 上报本会话积分（header: game/score；服务器累加后广播）
    FISH_BOARD = "fish_board"      # 排行榜（请求 header: game → 单播；积分变更时广播 game/entries）
    # R52 头像与个人资料（昵称=登录标识不可改；头像/签名/密码可改）
    AVATAR_SET = "avatar_set"    # 上传头像（header: ext；body=图片字节；服务器回 AVATAR_DATA）
    AVATAR_DEL = "avatar_del"    # 删除头像（服务器回 AVATAR_DATA ext=""）
    AVATAR_GET = "avatar_get"    # 拉取头像（header: uid → 服务器单播 AVATAR_DATA）
    AVATAR_DATA = "avatar_data"  # 头像回帧（header: uid/ext；body=字节；ext=""=无头像）
    SIGN_SET = "sign_set"        # 设置个性签名（header: sign；服务器广播 roster 更新）
    # R69C9 好友备注名（本人视角，服务器按 owner 持久化；remark 空=清除）
    REMARK_SET = "remark_set"    # header: uid/remark（remark 长度≤24）
    REMARK_ACK = "remark_ack"    # 服务器回执（header: uid/remark）
    # R53 服务器管理员（最高清理权限；凭据由部署侧配置）
    ADMIN_KICK = "admin_kick"    # 踢人下线（header: uid；仅管理员）
    CLEAR_ALL = "clear_all"      # 清空全部聊天记录（仅管理员；服务器广播 CLEARED all）
    CLEAR_UID = "clear_uid"      # 清空指定用户全部消息（header: uid；仅管理员；广播 CLEARED uid）
    CLEARED = "cleared"          # 服务器广播：{all: true} 或 {uid} → 客户端清本地历史

    # 系统管理员群管理：目录 + 增删成员 + 解散群
    ADMIN_GROUPS = "admin_groups"        # 管理员：拉取全部群+成员花名册（服务器回 ADMIN_GROUPS_ROSTER）
    ADMIN_GROUPS_ROSTER = "admin_groups_roster"  # 回帧：{groups:[{gid,name,kind,public,owner,
                                             #          admins,member_count,members:[{uid,nick}]}]}
    ADMIN_GROUP_SET = "admin_group_set"  # 管理员：增删成员/解散群 header{gid,op=add|remove|dissolve,uid}
    ADMIN_USER_GET = "admin_user_get"   # 管理员：查某人信息+所属群（header uid/known；回 ADMIN_USER_INFO）
    ADMIN_USER_INFO = "admin_user_info" # 回帧：{uid,nick,online,groups:[{gid,name,role}]}
    ADMIN_USER_DEL = "admin_user_del"   # 管理员：清除用户（删除账号 header uid/known；清其消息、移出全部群）
    INV_SET = "invis_set"           # 隐身上线开关（header on；服务器按 uid 权威持久，仅广播他人可见名单过滤）
    INV_ACK = "invis_ack"           # 回帧：{on}；已生效
    ADMIN_INVIS_SET = "admin_invis_set"  # R56B：管理员强制显身/隐身（header uid,on；服务器校验）
    STATUS_SET = "status_set"       # R68：在线状态（header status=online/away/busy；服务器按 uid 持久并广播 roster）

    # 朋友圈（图文动态时间轴；复用广播+快照）
    MOMENT_PUBLISH = "moment_publish"     # 发动态（header: text,n_imgs；body=依次多张图片字节）
    MOMENT_LIKE = "moment_like"           # 点赞/取消（header: pid,on）
    MOMENT_COMMENT = "moment_comment"     # 评论（header: pid,text）
    MOMENT_DEL = "moment_del"             # 删除自己的动态（header: pid；服务器校验 uid）
    MOMENT_FEED = "moment_feed"           # 拉全量时间轴（服务器回下帧）
    MOMENT_NEW = "moment_new"             # 服务器广播：新动态（header/post 序列化到 body JSON）
    MOMENT_UPDATE = "moment_update"       # 服务器广播：pid+likes/comments 最新（body JSON {pid,post}）
    MOMENT_DATA = "moment_data"           # 图片回帧（header: fn/ext，body=字节；fn=文件名）
    MOMENT_IMG_GET = "moment_img_get"     # 拉取动态图片（header: fn → 服务器回 MOMENT_DATA）
    MOMENT_COVER_SET = "moment_cover_set"  # 设置朋友圈封面（header: preset 或 ext；body=图片字节）
    MOMENT_COVER_GET = "moment_cover_get"  # 拉取我的封面（服务器回 MOMENT_COVER，img 模式带 body）
    MOMENT_COVER_DEL = "moment_cover_del"  # 恢复默认封面
    MOMENT_COVER = "moment_cover"          # 封面回帧/广播（header: uid/cover；img 模式 body=字节）

    # R69B6/B7 群待办 / 接龙 / 签到（统一 TASK_*；权威在服务器 tasks，广播 TASK_STATE）
    TASK_ADD = "task_add"        # 发起（header: gid/text/mode/assignee → 分配 tid，广播 TASK_STATE）
    TASK_DO = "task_do"          # 参与/打卡（header: gid/tid/on；on=0 撤销参与）
    TASK_LIST = "task_list"      # 拉取清单（header: gid → 单播 TASK_STATE）
    TASK_DEL = "task_del"        # 关闭/删除（header: gid/tid；发起人/群主/管理员）
    TASK_STATE = "task_state"    # 群任务清单（header: gid/tasks/text；老客户端按普通广播忽略）

    # 伪装流量
    PADDING = "padding"


class ProtocolError(Exception):
    """协议错误：调用方应断开连接"""


def encode_frame(header: dict, body: bytes = b"") -> bytes:
    """编码一帧（未加密前的明文帧）。header 必须含 t；body_len 自动填充。"""
    h = dict(header)
    h["body_len"] = len(body)
    payload = json.dumps(h, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return struct.pack(">I", len(payload)) + payload + body


class FrameReader:
    """流式拆帧：逐字节喂入，吐出完整帧 (header_dict, body_bytes)。

    处理半包与粘包；任何格式/超限错误抛 ProtocolError。
    """

    def __init__(self, max_header: int = CFG.max_header_bytes,
                 max_body: int = CFG.max_body_bytes) -> None:
        self._buf = bytearray()
        self._max_header = max_header
        self._max_body = max_body

    def feed(self, data: bytes) -> list:
        """喂入网络数据，返回 [(header, body), ...]"""
        self._buf.extend(data)
        frames = []
        while True:
            frame = self._try_read_one()
            if frame is None:
                return frames
            frames.append(frame)

    def _try_read_one(self):
        if len(self._buf) < 4:
            return None
        header_len = struct.unpack(">I", bytes(self._buf[:4]))[0]
        if header_len > self._max_header:
            raise ProtocolError(f"header too long: {header_len}")
        if len(self._buf) < 4 + header_len:
            return None
        raw_header = bytes(self._buf[4:4 + header_len])
        try:
            header = json.loads(raw_header.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ProtocolError(f"bad json header: {exc}") from exc
        if not isinstance(header, dict) or "t" not in header:
            raise ProtocolError("missing t field")
        b_raw = header.get("body_len", 0)
        if isinstance(b_raw, bool) or not isinstance(b_raw, (int, str)):
            raise ProtocolError("bad body_len")
        try:
            body_len = int(b_raw)
        except (TypeError, ValueError):
            raise ProtocolError("bad body_len") from None
        if body_len < 0 or body_len > self._max_body:
            raise ProtocolError(f"bad body_len: {body_len}")
        total = 4 + header_len + body_len
        if len(self._buf) < total:
            return None
        body = bytes(self._buf[4 + header_len:total])
        del self._buf[:total]
        return header, body
