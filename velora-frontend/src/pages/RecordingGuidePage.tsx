import { useEffect, useState } from 'react'
import { ChevronRight, MessageCircle, ShieldCheck, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

const topicCards = [
  {
    title: '장보기와 저녁 준비',
    question: '오늘 저녁은 뭐 드실 거예요? 마트에 가면 무엇을 사야 할까요?',
    points: '물건 기억, 순서 설명, 단어 선택',
    example: {
      title: '장보기와 저녁 준비 대화 예시',
      context: '자녀가 부모님께 오늘 저녁 메뉴와 장볼 물건을 자연스럽게 묻는 전화통화입니다.',
      duration: '약 1분 ~ 1분 30초',
      lines: [
        ['자녀', '엄마, 오늘 저녁에는 뭐 드실 생각이세요?'],
        ['부모', '오늘은 된장찌개를 끓여 먹으려고 해. 냉장고를 보니까 두부는 조금 남아 있는데, 애호박하고 버섯이 없더라. 그래서 오후에 마트에 가서 애호박, 버섯, 계란을 사오려고 해.'],
        ['자녀', '그럼 장볼 건 애호박, 버섯, 계란이네요?'],
        ['부모', '응, 맞아. 그리고 우유도 거의 떨어졌으니까 우유도 하나 사면 좋겠어. 우유는 무거우니까 작은 걸로 하나만 사려고 해.'],
        ['자녀', '마트에 가시면 어떤 순서로 보실 거예요?'],
        ['부모', '먼저 채소 코너에서 애호박하고 버섯을 고르고, 그다음에 계란을 보고, 마지막에 우유를 사면 될 것 같아. 집에 오면 바로 찌개를 끓이고 남은 반찬하고 같이 먹으면 되지.'],
        ['자녀', '아까 말씀하신 장볼 물건을 다시 한번 말해주실 수 있어요?'],
        ['부모', '애호박, 버섯, 계란, 그리고 우유였지. 이렇게 적어두면 빠뜨리지 않을 것 같아.'],
        ['자녀', '네, 다녀오실 때 천천히 다녀오세요.'],
        ['부모', '그래. 마트 다녀와서 전화할게.'],
      ],
    },
  },
  {
    title: '병원 예약과 약 복용',
    question: '이번 주 병원 예약이 언제였죠? 약은 드셨어요?',
    points: '시간 기억, 일정 회상, 준비물 계획',
    example: {
      title: '병원 예약과 약 복용 통화 예시',
      context: '자녀가 부모님께 병원 예약, 출발 시간, 약 복용 여부, 준비물을 자연스럽게 확인하는 전화통화입니다.',
      duration: '약 1분 ~ 1분 30초',
      lines: [
        ['자녀', '아버지, 이번 주 병원 예약이 언제였죠?'],
        ['부모', '병원 예약이... 이번 주 금요일이었던 것 같아. 잠깐만, 달력에 적어둔 걸 보면 정확한데. 여기 보니까 금요일 오전 열 시 반이네. 내가 아까는 목요일인가 했는데, 금요일이 맞아.'],
        ['자녀', '그럼 몇 시쯤 집에서 나가시면 좋을까요?'],
        ['부모', '열 시 반 예약이면 아홉 시 반쯤 나가면 될 것 같아. 버스를 타면 한 번에 가는데 기다리는 시간이 있을 수 있으니까 조금 일찍 나가는 게 좋겠지.'],
        ['자녀', '오늘 아침 약은 드셨어요?'],
        ['부모', '먹은 것 같아. 아침 먹고 물컵을 식탁에 놨던 기억이 나거든. 그런데 표시를 했는지는 잘 모르겠네. 요즘은 약 먹고 나면 달력에 표시하려고 하는데 가끔 잊어버려.'],
        ['자녀', '그럼 약 봉투를 한번 확인해 보시면 되겠네요.'],
        ['부모', '응, 약 봉투를 보면 알 수 있어. 아침 약 봉지가 비어 있으면 먹은 거니까. 이렇게 확인하면 마음이 좀 놓여.'],
        ['자녀', '병원 갈 때 챙길 것은 뭐가 있을까요?'],
        ['부모', '신분증하고 검사 결과지, 약 봉투. 그리고 예약 시간은 금요일 오전 열 시 반. 내가 냉장고 옆에 크게 적어둘게.'],
        ['자녀', '네, 전날 다시 한번 전화드릴게요.'],
        ['부모', '그래, 그렇게 해주면 고맙지. 다녀와서 연락할게.'],
      ],
    },
  },
  {
    title: '오늘 하루와 현재 상황',
    question: '오늘 하루 어떻게 보내셨어요? 식사는 하셨어요?',
    points: '최근 기억, 현재 인식, 대화 유지',
    example: {
      title: '오늘 하루와 현재 상황 통화 예시',
      context: '자녀가 부모님께 오늘 하루, 식사 여부, 현재 위치, 내일 일정을 자연스럽게 확인하는 전화통화입니다.',
      duration: '약 1분 ~ 1분 30초',
      lines: [
        ['자녀', '엄마, 오늘 하루 어떻게 보내셨어요?'],
        ['부모', '아침에 일어나서 물을 한 잔 마시고 창밖을 봤어. 날씨가 괜찮아서 빨래를 돌렸던 것 같아. 그리고 잠깐 밖에 나갔다 온 것 같은데, 마트였는지 은행이었는지 조금 헷갈리네. 아마 마트에 다녀온 것 같아. 장바구니가 현관에 있으니까.'],
        ['자녀', '마트에서는 뭐 사셨어요?'],
        ['부모', '계란하고 두부를 산 것 같아. 우유도 사려고 했는데 샀는지는 잘 모르겠네. 냉장고를 보면 알 수 있을 것 같아. 요즘은 장볼 것을 적어두지 않으면 하나씩 빠뜨릴 때가 있어서 휴대폰에 메모해 두려고 해.'],
        ['자녀', '식사는 하셨어요?'],
        ['부모', '점심은 먹었어. 밥하고 김치, 그리고 남은 국을 데워 먹었어. 그런데 저녁은 아직 안 먹은 것 같아. 조금 전에 뭘 먹은 것 같기도 한데 정확히는 모르겠네. 식탁을 보면 알 수 있을 것 같아.'],
        ['자녀', '지금은 집에 계신 거죠?'],
        ['부모', '응, 집에 있어. 현관 옆에 장바구니도 있고, 거실에 앉아 있어. 그런데 오늘이 수요일인지 목요일인지 잠깐 헷갈리네. 달력을 한번 봐야겠다.'],
        ['자녀', '괜찮아요. 천천히 확인하시면 돼요. 내일은 어떤 일정이 있으세요?'],
        ['부모', '내일은 특별한 일정은 없고, 오전에 산책을 조금 하려고 해. 그리고 우유를 안 샀으면 마트에 다시 다녀와야지.'],
      ],
    },
  },
]

interface RecordingGuidePageProps {
  onComplete?: () => void
  onBackIntercept?: (handler: (() => boolean) | null) => void
}

export default function RecordingGuidePage({ onComplete, onBackIntercept }: RecordingGuidePageProps) {
  const [openExample, setOpenExample] = useState<(typeof topicCards)[number]['example'] | null>(null)
  const [view, setView] = useState<'principles' | 'topics'>('principles')

  useEffect(() => {
    if (!onBackIntercept) return
    if (view === 'topics') {
      onBackIntercept(() => {
        setView('principles')
        return true
      })
      return () => onBackIntercept(null)
    }
    onBackIntercept(null)
    return () => onBackIntercept(null)
  }, [onBackIntercept, view])

  return (
    <div className="space-y-3 pt-1">
      {view === 'principles' ? (
        <>
          <section className="rounded-[22px] border border-[#dce9e6] bg-white p-3 shadow-sm shadow-teal-950/5">
            <div className="space-y-1.5">
              {[
                '조용한 곳에서 평소 말하듯 자연스럽게 녹음합니다.',
                '자녀 음성은 30~60초, 내 목소리는 30~60초 정도면 충분합니다.',
                '부모님과의 통화녹음은 1분~1분 30초 정도로 준비합니다.',
                '질문은 짧게 하고, 상대가 충분히 말할 수 있게 기다립니다.',
                '말이 잠깐 멈추거나 헷갈려도 바로 정정하지 않고 이어갑니다.',
                '분석 결과는 진단이 아닌 참고 신호로만 사용합니다.',
              ].map(item => (
                <p key={item} className="rounded-xl bg-[#f7fbfa] px-3 py-2.5 text-[17px] font-bold leading-[1.38] text-[#426160]">
                  {item}
                </p>
              ))}
            </div>
          </section>

          <button
            type="button"
            onClick={() => setView('topics')}
            className="flex w-full items-center justify-between rounded-[20px] border border-[#dce9e6] bg-white px-4 py-3.5 text-left shadow-sm shadow-teal-950/5"
          >
            <div className="flex min-w-0 items-center gap-3">
              <MessageCircle className="h-6 w-6 shrink-0 text-[#0f7d82]" />
              <span className="text-[17px] font-black text-[#183f40]">전화 대화 주제 보기</span>
            </div>
            <ChevronRight className="h-6 w-6 shrink-0 text-[#8aa09e]" />
          </button>

          {onComplete && (
            <Button
              onClick={onComplete}
              className="h-16 w-full rounded-full bg-[#0f7d82] text-[18px] font-black text-white shadow-none hover:bg-[#0b6f74]"
            >
              서비스 선택으로 이동
            </Button>
          )}
        </>
      ) : (
        <section className="space-y-2">
          <div className="flex items-center gap-2 px-1">
            <MessageCircle className="h-6 w-6 text-[#0f7d82]" />
            <p className="text-[17px] font-black text-[#183f40]">전화 대화 주제</p>
          </div>
          {topicCards.map(topic => (
            <button
              key={topic.title}
              onClick={() => topic.example && setOpenExample(topic.example)}
              className="w-full rounded-[22px] border border-[#e3ece9] bg-white p-4 text-left shadow-sm shadow-teal-950/5"
              aria-label={topic.example ? `${topic.title} 대화 예시 보기` : topic.title}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[18px] font-black text-[#183f40]">{topic.title}</p>
                  <p className="mt-2 text-[17px] font-bold leading-[1.5] text-[#426160]">{topic.question}</p>
                </div>
                {topic.example && <ChevronRight className="mt-0.5 h-6 w-6 shrink-0 text-[#8aa09e]" />}
              </div>
              <p className="mt-3 rounded-xl bg-[#f7fbfa] px-3 py-3 text-[16px] font-bold leading-[1.5] text-[#6f8785]">{topic.points}</p>
            </button>
          ))}
          {onComplete && (
            <Button
              onClick={onComplete}
              className="mt-3 h-16 w-full rounded-full bg-[#0f7d82] text-[18px] font-black text-white shadow-none hover:bg-[#0b6f74]"
            >
              서비스 선택으로 이동
            </Button>
          )}
        </section>
      )}

      <p className="flex items-start gap-3 rounded-2xl bg-[#f7fbfa] px-4 py-4 text-[16px] font-bold leading-[1.5] text-[#7d9593]">
        <ShieldCheck className="mt-1 h-6 w-6 shrink-0 text-[#0f7d82]" />
        걱정되는 변화가 지속되면 치매안심센터, 병원, 전문 의료진과 상담해 주세요.
      </p>

      {openExample && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/35 px-3" onClick={() => setOpenExample(null)}>
          <section
            className="max-h-[82vh] w-full max-w-[430px] overflow-hidden rounded-t-[28px] bg-[#fbfdfb] shadow-2xl shadow-black/20"
            onClick={event => event.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3 border-b border-[#e3ece9] px-5 py-4">
              <div>
                <p className="text-[18px] font-black text-[#183f40]">{openExample.title}</p>
                <p className="mt-2 text-[16px] font-bold leading-[1.5] text-[#607b79]">상황: {openExample.context}</p>
                <p className="mt-1 text-[16px] font-bold leading-[1.5] text-[#607b79]">목표 시간: {openExample.duration}</p>
              </div>
              <button
                onClick={() => setOpenExample(null)}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[#0f7d82] hover:bg-[#e8f3f1]"
                aria-label="예시 닫기"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="max-h-[62vh] space-y-2 overflow-y-auto px-5 py-4">
              {openExample.lines.map(([speaker, text], index) => (
                <div key={`${speaker}-${index}`} className="rounded-xl bg-[#f1f8f6] px-3 py-2">
                  <p className="text-[15px] font-black text-[#0f7d82]">{speaker}</p>
                  <p className="mt-1 text-[17px] font-bold leading-[1.5] text-[#315d52]">{text}</p>
                </div>
              ))}
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
