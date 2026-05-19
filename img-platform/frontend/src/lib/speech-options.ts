export const speechVoices = [
  { id: 'male-qn-qingse', name: '青涩青年-男' },
  { id: 'female-shaonv', name: '少女-女' },
  { id: 'audiobook_male_1', name: '有声书男声1' },
]

export const speechEmotions = [
  { id: 'auto', name: '自动' },
  { id: 'happy', name: '开心' },
  { id: 'sad', name: '悲伤' },
  { id: 'angry', name: '愤怒' },
  { id: 'fearful', name: '恐惧' },
  { id: 'disgusted', name: '厌恶' },
  { id: 'surprised', name: '惊讶' },
  { id: 'calm', name: '中性' },
  { id: 'fluent', name: '生动' },
  { id: 'whisper', name: '低语' },
]

export const speechInterjections = [
  { tag: '(laughs)', label: '笑声' },
  { tag: '(chuckle)', label: '轻笑' },
  { tag: '(coughs)', label: '咳嗽' },
  { tag: '(clear-throat)', label: '清嗓子' },
  { tag: '(groans)', label: '呻吟' },
  { tag: '(breath)', label: '换气' },
  { tag: '(pant)', label: '喘气' },
  { tag: '(inhale)', label: '吸气' },
  { tag: '(exhale)', label: '呼气' },
  { tag: '(gasps)', label: '倒吸气' },
  { tag: '(sniffs)', label: '吸鼻子' },
  { tag: '(sighs)', label: '叹气' },
  { tag: '(snorts)', label: '喷鼻息' },
  { tag: '(burps)', label: '打嗝' },
  { tag: '(lip-smacking)', label: '咂嘴' },
  { tag: '(humming)', label: '哼唱' },
  { tag: '(hissing)', label: '嘶嘶声' },
  { tag: '(emm)', label: '嗯' },
  { tag: '(sneezes)', label: '喷嚏' },
]

export const speechAudioFormats = ['mp3', 'wav', 'pcm', 'flac'] as const
export const speechSampleRates = [8000, 16000, 22050, 24000, 32000, 44100] as const
export const speechBitrates = [32000, 64000, 128000, 256000] as const

export const speechLanguageBoosts = [
  { id: '', name: '不启用' },
  { id: 'auto', name: '自动识别' },
  { id: 'Chinese', name: '中文' },
  { id: 'Chinese,Yue', name: '粤语' },
  { id: 'English', name: '英语' },
  { id: 'Japanese', name: '日语' },
  { id: 'Korean', name: '韩语' },
  { id: 'Spanish', name: '西班牙语' },
  { id: 'French', name: '法语' },
  { id: 'German', name: '德语' },
  { id: 'Portuguese', name: '葡萄牙语' },
  { id: 'Russian', name: '俄语' },
  { id: 'Arabic', name: '阿拉伯语' },
]

export const speechVoiceEffects = [
  { id: '', name: '无音效' },
  { id: 'spacious_echo', name: '空旷回音' },
  { id: 'auditorium_echo', name: '礼堂广播' },
  { id: 'lofi_telephone', name: '电话失真' },
  { id: 'robotic', name: '电音' },
]
