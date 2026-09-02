// Classification scores display: L1 / L2 / L3 with numeric values.
export default function ClassificationScores({ l1, l2, l3 }) {
  const score = (v) => v != null ? `${v.toFixed(2)}` : "—";

  return (
    <div className="classification-scores">
      <span className="scores__label">分类分数</span>
      <div className="scores__items">
        <span className="scores__item">{`L1 ${score(l1)}`}</span>
        <span className="scores__item">{`L2 ${score(l2)}`}</span>
        <span className="scores__item">{`L3 ${score(l3)}`}</span>
      </div>
    </div>
  );
}