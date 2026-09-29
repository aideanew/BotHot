import { useEffect } from "react";

// 所有 page.tsx 都是 "use client"，无法 export metadata——缺这层时 7 个页签里有 6 个
// 都显示根 layout 的「BotHot · 知识空间」。放在组件首行、早退分支之前，早退态也有正确标题。
export function usePageTitle(pageTitle: string) {
  useEffect(() => {
    document.title = `${pageTitle} · BotHot`;
  }, [pageTitle]);
}
