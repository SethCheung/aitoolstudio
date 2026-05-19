export const musicTemplates = [
  {
    name: '民谣情歌',
    prompt: '独立民谣,忧郁,内省,渴望,独自漫步,咖啡馆',
    lyrics: '[Verse]\n街灯微亮晚风轻抚\n影子拉长独自漫步\n旧外套裹着深深忧郁\n不知去向渴望何处\n\n[Chorus]\n推开木门香气弥漫\n熟悉的角落陌生人看\n咖啡苦涩思念渐暖\n你的笑容藏在心间',
  },
  {
    name: '流行励志',
    prompt: '流行音乐,励志,充满希望,青春,追梦',
    lyrics: '[Verse]\n天空很高 梦想很远\n脚步不停 向前向前\n跌倒了就站起来\n擦干眼泪继续精彩\n\n[Chorus]\n我相信明天会更好\n每一步都在发光\n不管风雨有多大\n心中的火焰不会灭',
  },
  {
    name: '电子舞曲',
    prompt: '电子音乐,EDM,派对,活力,夜店,节奏感强',
    lyrics: "[Intro]\nLet's go!\n\n[Verse]\n灯光闪烁 节奏跳动\n今夜不眠 尽情放纵\n音乐响起 身体舞动\n忘记烦恼 享受轻松\n\n[Chorus]\n跟着节奏一起跳\n让音乐带你飞翔\n放开一切的束缚\n今夜属于你和我",
  },
  {
    name: '古风情怀',
    prompt: '古风,中国风,唯美,诗意,江南,琵琶',
    lyrics: '[Verse]\n烟雨江南 青石巷\n油纸伞下 谁彷徨\n琵琶声声 诉衷肠\n一曲相思 泪两行\n\n[Chorus]\n梦回千年 画中人\n笔墨挥洒 情意深\n愿化春风 轻吹过\n带去思念 到你心',
  },
  {
    name: '摇滚青春',
    prompt: '摇滚,热血,叛逆,青春,吉他,激情',
    lyrics: '[Verse]\n不要说我们太年轻\n不要说我们不懂事\n心中有火就要燃烧\n青春就要活出精彩\n\n[Chorus]\n我们不需要别人定义\n我们要自己书写故事\n摇滚精神永不熄灭\n这就是我们的态度',
  },
]

export const musicStructureTags = [
  '[Intro]',
  '[Verse]',
  '[Pre Chorus]',
  '[Chorus]',
  '[Bridge]',
  '[Outro]',
  '[Interlude]',
  '[Hook]',
  '[Inst]',
]

export const musicAudioFormats = ['mp3', 'wav', 'pcm'] as const
export const musicOutputFormats = ['hex', 'url'] as const
export const musicSampleRates = [16000, 24000, 32000, 44100] as const
export const musicBitrates = [32000, 64000, 128000, 256000] as const
