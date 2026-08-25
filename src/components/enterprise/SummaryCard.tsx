import "./SummaryCard.css";
export type SummaryCardTone = "neutral" | "good" | "warning" | "danger" | "info";
interface Props { label:string; value:string; detail?:string; tone?:SummaryCardTone; icon?:string; }
export default function SummaryCard({label,value,detail,tone="neutral",icon}:Props){return <article className={`summary-card summary-card--${tone}`}><div className="summary-card__heading">{icon?<span>{icon}</span>:null}<span>{label}</span></div><strong className="summary-card__value">{value}</strong>{detail?<small>{detail}</small>:null}</article>}
