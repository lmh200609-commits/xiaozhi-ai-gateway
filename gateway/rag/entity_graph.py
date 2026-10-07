"""
Railway Theme Park Domain Entity Graph & Multi-Modal Assets.
Links textual knowledge to physical exhibition zones and multimedia triggers (video, audio, kiosk).
"""
import re
from typing import Dict, Any, List, Optional

class RailwayEntity:
    def __init__(
        self,
        entity_id: str,
        name: str,
        category: str,
        aliases: List[str],
        zone: str,
        location_desc: str,
        video_id: Optional[str] = None,
        video_title: Optional[str] = None,
        summary: str = "",
        key_facts: List[str] = None
    ):
        self.entity_id = entity_id
        self.name = name
        self.category = category
        self.aliases = [a.lower() for a in ([name] + aliases)]
        self.zone = zone
        self.location_desc = location_desc
        self.video_id = video_id
        self.video_title = video_title
        self.summary = summary
        self.key_facts = key_facts or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "name": self.name,
            "category": self.category,
            "aliases": self.aliases,
            "zone": self.zone,
            "location_desc": self.location_desc,
            "has_multimedia": bool(self.video_id),
            "video_id": self.video_id,
            "video_title": self.video_title,
            "summary": self.summary,
            "key_facts": self.key_facts
        }

# Pre-defined Core Railway Park Entity Graph (中国·大安机车博览园核心实体图谱)
CORE_RAILWAY_ENTITIES = [
    RailwayEntity(
        entity_id="daan_locomotive_expo",
        name="中国·大安机车博览园",
        category="园区总体概览",
        aliases=[
            "中国大安机车博览园", "大安机车博览园", "大安机车园", "大安火车园区", "白城火车园区",
            "大安机车", "大安博览园", "机车博览园", "机车封存基地", "沈阳局大安", "大安北机务段",
            "三场两馆一线一平台", "大安北", "大安", "园区", "博览园"
        ],
        zone="园区全景",
        location_desc="吉林省白城市大安市糖厂路（沈阳铁路局大安机车封存基地东侧）",
        video_id="daan_park_vlog",
        video_title="大安机车博览园实景探秘与全园导览Vlog",
        summary="世界规模最大、机车存放台数最多的园林式机车陈列景区，全国唯一的机车封存基地，占地约14万平方米，荣获最大规模蒸汽机车展示世界级荣誉。",
        key_facts=[
            "占地约14万平方米，于2025年5月1日正式开园，是全国唯一的国家级机车战略封存基地",
            "总体布局为'三场两馆一线一平台'：火车头广场、内燃机车广场、蒸汽机车广场；记忆馆、体验馆；环园观光小火车专线；全景观景平台",
            "馆藏核心资产包括76台蒸汽机车群、22台内燃机车、3台电力机车，创下世界最大规模蒸汽机车展世界纪录",
            "传承东北老工业基地精神与铁路红色基因，设有毛泽东号、朱德号光辉档案及黄继光号等功勋机车实物展"
        ]
    ),
    RailwayEntity(
        entity_id="zhude_locomotive",
        name="朱德号机车",
        category="历史功勋机车",
        aliases=["朱德号", "朱德浩", "朱德机车", "朱德号机车", "朱德", "jf1191", "jf-1191", "解放1191", "双子星机车"],
        zone="记忆馆与红色功勋展区",
        location_desc="记忆馆功勋展厅及蒸汽机车同源方阵",
        video_id=None,
        video_title=None,
        summary="1946年10月在哈尔滨机务段命名，与毛泽东号并称中国铁路'双子星'英雄机车，历经五次技术换型，现作为干线大功率机车运行。",
        key_facts=[
            "1946年10月由哈尔滨机务段工人在极端艰苦条件下抢修修复并命名，第一代为解放型(JF)1191号蒸汽机车",
            "在解放战争辽沈战役、平津战役和抗美援朝中勇挑重担，以'敢打硬仗、敢破纪录'的钢铁精神闻名全路",
            "历经五次换型：解放型蒸汽(JF1191) -> 东风4(DF4) -> 东风11G(DF11G) -> 和谐3D(HXD3D) -> 复兴型(FXD3B)大功率电力机车",
            "大安机车博览园地处白山黑水铁路枢纽，记忆馆详尽展出朱德号战功与档案，蒸汽机车广场陈列有朱德号同源的解放型、前进型蒸汽机车方阵"
        ]
    ),
    RailwayEntity(
        entity_id="mzd_locomotive",
        name="毛泽东号机车",
        category="历史功勋机车",
        aliases=["毛泽东号", "毛泽东浩", "毛泽东机车", "毛主席号", "八一号", "解放型", "jf304", "jf-304", "解放304", "毛泽东"],
        zone="记忆馆与红色功勋展区",
        location_desc="记忆馆第一展厅功勋展台及蒸汽广场同款车群",
        video_id="mzd_steam",
        video_title="毛泽东号机车峥嵘岁月与英雄历程",
        summary="1946年诞生于哈尔滨机务段，中国第一台以领袖命名的英雄机车，与朱德号并称双子星，被誉为中国铁路第一车。",
        key_facts=[
            "1946年10月由哈尔滨机务段工人自力更生修复并命名，原型为解放型(JF)304号蒸汽机车",
            "经历辽沈战役、平津战役及抗美援朝战争支前运输，后调入北京铁路局丰台机务段",
            "历经蒸汽、东风4、东风11、和谐3B、和谐3D等五次技术换型，至今保持全路安全行驶数百万公里的最高纪录",
            "在大安机车博览园记忆馆特设毛泽东号光辉展区，广场并列展示着同年代解放型与前进型庞大机车巨阵"
        ]
    ),
    RailwayEntity(
        entity_id="steam_fleet_76",
        name="76台蒸汽机车群",
        category="世界纪录展项",
        aliases=["76台", "76台蒸汽机车", "蒸汽机车方阵", "蒸汽机车群", "最大规模蒸汽机车", "蒸汽机车广场", "前进型群", "钢铁巨龙", "机车方阵"],
        zone="蒸汽机车广场",
        location_desc="蒸汽机车广场核心陈列区（两列长排钢铁方阵）",
        video_id="qianjin_steam",
        video_title="大安博览园76台蒸汽机车钢铁长阵·工业奇迹",
        summary="大安机车博览园的王牌景观，整齐封存展出76台退役蒸汽机车，荣获世界最大规模蒸汽机车展荣誉。",
        key_facts=[
            "共集中封存展出76台原汁原味的蒸汽机车，以两列并排的形式延伸数百米，气势极其恢弘震撼",
            "涵盖前进型(QJ)、建设型(JS)、上游型(SY)等多种新中国主力蒸汽机车型号",
            "依托原沈阳局大安北机车封存保养基地优越的自然条件，保存状态极其完好，零件完备",
            "是全球铁路摄影发烧友、工业历史学者和研学旅行必到的世界级打卡胜地"
        ]
    ),
    RailwayEntity(
        entity_id="huangjiguang_locomotive",
        name="黄继光号机车",
        category="历史功勋机车",
        aliases=["黄继光号", "黄继光浩", "黄继光机车", "黄继光", "特级英雄机车"],
        zone="功勋机车展区",
        location_desc="博览园功勋展示线核心位",
        video_id=None,
        video_title=None,
        summary="大安机车博览园馆藏的重点英雄机车之一，传承特级英雄黄继光的英勇无畏与奉献精神。",
        key_facts=[
            "以抗美援朝特级英雄黄继光烈士命名，承载着中国铁路职工'听党指挥、敢打必胜'的红色传统",
            "在大安机车博览园进行永久珍藏展出，是开展青少年爱国主义与国防科技教育的核心实物教材"
        ]
    ),
    RailwayEntity(
        entity_id="v100_diesel",
        name="德制V100型内燃机车",
        category="珍稀进口机车",
        aliases=["v100", "v100型", "德制v100", "德制机车", "德国机车", "进口内燃机车"],
        zone="内燃机车广场",
        location_desc="内燃机车广场特色展台",
        video_id=None,
        video_title=None,
        summary="大安机车博览园珍藏的罕见德国原装进口液力传动内燃机车，国内极其稀有的工业珍品。",
        key_facts=[
            "原产于德国，采用先进的液力传动系统和重型工业制造工艺，在国际铁道史上声名显赫",
            "是大安机车博览园22台内燃机车中独一无二的稀缺藏品，极具工业遗产研究与观赏价值"
        ]
    ),
    RailwayEntity(
        entity_id="df4_diesel",
        name="东风4型内燃机车",
        category="内燃动力机车",
        aliases=["东风4", "东风4d", "东风4b", "东风", "df4", "内燃机车", "绿皮车", "绿皮火车", "客运内燃"],
        zone="内燃机车广场",
        location_desc="内燃机车广场重载展示线",
        video_id="df4_diesel",
        video_title="东风浩荡·内燃机车与绿色干线时代",
        summary="大连机车厂制造的经典内燃机车，大安博览园展示有东风4D、东风5、东风7、东风8等22台完整内燃谱系。",
        key_facts=[
            "大安机车博览园内燃机车广场封存有东风4D、东风5、东风7、东风8、东方红2、东方红5等22台内燃主力",
            "经典东风4涂装包括西瓜绿、橘子黄、乌克兰蓝等，曾承担全国数十年绿皮旅客列车与重载货运",
            "见证中国铁路从蒸汽动力全面跨入内燃大提速的辉煌时代"
        ]
    ),
    RailwayEntity(
        entity_id="cr400_fuxing",
        name="复兴号智能动车组",
        category="现代高速动车组",
        aliases=["复兴号", "中国高铁", "cr400", "cr400af", "cr400bf", "智能动车组", "高铁", "动车", "和谐号"],
        zone="体验馆与高铁交互展区",
        location_desc="体验馆数字化沉浸展区",
        video_id="cr400_fuxing",
        video_title="复兴号智能动车组与中国高铁新纪元",
        summary="中国完全自主知识产权的高速动车组，商业运营速度时速350公里世界第一。",
        key_facts=[
            "2017年6月在京沪高铁首发，实现中国标准全自主研发",
            "智能型搭载千余项传感器，具备故障自诊断与自动驾驶辅助",
            "博览园体验馆配有复兴号驾驶交互演示与沉浸式声光电科普"
        ]
    ),
    RailwayEntity(
        entity_id="park_experience_hall",
        name="体验馆与模拟驾驶舱",
        category="互动体验展馆",
        aliases=["体验馆", "模拟驾驶", "驾驶体验", "开火车", "模拟舱", "互动体验", "体验区"],
        zone="体验馆",
        location_desc="博览园主体验馆一层交互中心",
        video_id=None,
        video_title=None,
        summary="大安机车博览园核心互动场馆，配备1:1机车真实驾驶模拟舱与多媒体动态演示系统。",
        key_facts=[
            "配备全仿真机车驾驶台，游客可坐在司机驾驶位推拉牵引手柄、控制制动闸瓦、鸣响汽笛",
            "大屏幕实时投射逼真的铁道行车视景，沉浸式体验在辽阔黑土地上驾驶万吨列车的震撼快感"
        ]
    ),
    RailwayEntity(
        entity_id="park_memory_hall",
        name="记忆馆与铁路发展史",
        category="历史科普展馆",
        aliases=["记忆馆", "历史馆", "展览馆", "大安北历史", "铁路史", "博物馆"],
        zone="记忆馆",
        location_desc="博览园主展馆记忆馆",
        video_id="jingzhang_railway",
        video_title="百年京张与中国铁路百年工业记忆",
        summary="全景展现中国百年机车工业演进史和大安北铁路枢纽历史沿革的核心展馆。",
        key_facts=[
            "系统展出从晚清老铁路、蒸汽时代、内燃电气化到高铁时代的珍贵历史文物、勋章与模型",
            "深度还原大安北机务段与战略封存基地数十年守护钢铁机车的奉献记忆与工人情怀"
        ]
    ),
    RailwayEntity(
        entity_id="park_service",
        name="中国·大安机车博览园游客服务指南",
        category="园区导览与服务",
        aliases=[
            "门票", "票价", "门票价格", "开放时间", "营业时间", "几点开门", "几点关门", "地址", "怎么去",
            "位置", "在哪", "交通", "拍照", "游览路线", "参观路线", "小火车", "观景台", "厕所", "洗手间", "餐饮"
        ],
        zone="游客服务中心与全园",
        location_desc="吉林省白城市大安市糖厂路主出入口",
        video_id=None,
        video_title=None,
        summary="中国·大安机车博览园游览实用全指南，含开放时间、交通导航、游园路线及便民设施。",
        key_facts=[
            "景区地址：吉林省白城市大安市糖厂路（沈阳铁路局大安机车封存基地东侧，自驾导航'大安机车博览园'，近大安北站）",
            "推荐游览路线：火车头广场迎宾打卡 -> 蒸汽机车广场观赏76台钢铁巨龙 -> 登上全景观景平台俯瞰全貌 -> 体验馆体验机车模拟驾驶 -> 记忆馆领略百年机车历史 -> 乘坐环园小火车惬意巡游",
            "开放时间：通常为 09:00 - 17:00（16:30停止入园，具体以景区当日公告为准）",
            "便民配套：配有大型生态停车场、母婴室、游客休憩文创驿站及无障碍通道"
        ]
    )
]

class RailwayEntityGraph:
    """Fast entity recognition and context linker for Railway Theme Park."""
    def __init__(self, entities: List[RailwayEntity] = None):
        self.entities = entities or CORE_RAILWAY_ENTITIES

    def match_entities(self, text: str) -> List[RailwayEntity]:
        """Matches all railway entities mentioned in user text (case-insensitive)."""
        text_clean = text.lower()
        matched = []
        for ent in self.entities:
            for alias in ent.aliases:
                if alias in text_clean:
                    matched.append(ent)
                    break
        return matched

    def get_entity_context(self, entity: RailwayEntity) -> str:
        """Returns structured prompt text for LLM injection."""
        facts_text = "\n".join([f"  - {f}" for f in entity.key_facts])
        video_hint = f"\n  - 关联展厅全屏视频：《{entity.video_title}》（视频代码: {entity.video_id}，可主动播放）" if entity.video_id else ""
        return (
            f"【展区与实体档案·{entity.name}】：\n"
            f"  - 所在展区：{entity.zone} ({entity.location_desc})\n"
            f"  - 核心概述：{entity.summary}\n"
            f"  - 关键考证事实：\n{facts_text}"
            f"{video_hint}"
        )

entity_graph = RailwayEntityGraph()
