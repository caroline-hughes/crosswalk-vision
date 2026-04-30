export function ReasonTagList({ tags }: { tags: string[] }) {
  return (
    <div className="tag-list" aria-label="Reason tags">
      {tags.map((tag) => (
        <span key={tag} className="tag">
          {tag}
        </span>
      ))}
    </div>
  );
}
