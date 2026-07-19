import { useEffect, useState } from 'react';
import { getNews } from '../api';
import type { NewsItem } from '../types';

export default function NewsRail() {
  const [items, setItems] = useState<NewsItem[]>([]);

  useEffect(() => {
    getNews()
      .then((r) => setItems(r.items))
      .catch(() => setItems([]));
    const t = setInterval(() => {
      getNews()
        .then((r) => setItems(r.items))
        .catch(() => undefined);
    }, 20000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="news-rail">
      <p className="rail-heading">News</p>
      <div className="news-list">
        {items.map((item, i) => (
          <article key={`${item.title}-${i}`} className={`news-card news-${item.kind}`}>
            <h3>{item.title}</h3>
            <p>{item.body}</p>
          </article>
        ))}
      </div>
    </div>
  );
}
