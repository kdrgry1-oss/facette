/**
 * IconSectionsPage — ikonlu, minimalist bilgi sayfası düzeni (İade & Değişim, İletişim...).
 * Sitenin ince/sans-serif fontlarıyla; başlık + aksan çizgisi, ikon + bölüm, altında
 * vurgulu "kart". İçerik StaticPage'den config olarak gelir.
 */
export default function IconSectionsPage({ title, intro, sections = [], card }) {
  const IconCircle = ({ Icon }) => (
    <span className="flex-shrink-0 w-12 h-12 md:w-14 md:h-14 rounded-full bg-neutral-100 flex items-center justify-center text-neutral-700">
      <Icon size={22} strokeWidth={1.4} />
    </span>
  );
  return (
    <>
      <h1 className="text-3xl md:text-5xl font-light tracking-tight text-black mb-3">{title}</h1>
      <div className="w-10 h-px bg-black/70 mb-6 md:mb-8" />
      {intro && (
        <p className="text-[15px] md:text-base leading-[1.7] text-neutral-700 font-light max-w-xl mb-8">{intro}</p>
      )}
      <div className="divide-y divide-neutral-200 border-t border-neutral-200">
        {sections.map((s, i) => (
          <div key={i} className="flex items-start gap-5 md:gap-7 py-6 md:py-7">
            <IconCircle Icon={s.Icon} />
            <div className="pt-1 min-w-0">
              <h2 className="text-[13px] md:text-sm tracking-[0.16em] uppercase text-black font-medium mb-3">{s.title}</h2>
              {s.lines && s.lines.map((l, j) => (
                <p key={j} className="text-[15px] leading-[1.75] text-neutral-700 font-light break-words">{l}</p>
              ))}
              {s.bullets && (
                <ul className="space-y-2.5 text-[15px] leading-[1.55] text-neutral-700 font-light">
                  {s.bullets.map((b, j) => (
                    <li key={j} className="flex gap-2.5">
                      <span className="mt-2 w-1 h-1 rounded-full bg-neutral-400 flex-shrink-0" />
                      <span>{b}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        ))}
      </div>
      {card && (
        <div className="mt-8 border border-neutral-200 rounded-xl p-6 md:p-8">
          <div className="flex items-start gap-5 md:gap-7">
            <IconCircle Icon={card.Icon} />
            <div className="pt-1 w-full min-w-0">
              <h2 className="text-[13px] md:text-sm tracking-[0.16em] uppercase text-black font-medium mb-3">{card.title}</h2>
              {card.lines.map((l, j) => (
                <p key={j} className="text-[15px] leading-[1.75] text-neutral-700 font-light">{l}</p>
              ))}
              {card.note && (
                <>
                  <hr className="my-4 border-neutral-200" />
                  <p className="text-[14px] leading-[1.7] text-neutral-500 font-light">{card.note}</p>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
