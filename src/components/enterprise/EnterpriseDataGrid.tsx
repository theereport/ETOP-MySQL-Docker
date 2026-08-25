import { useMemo, useState } from "react";
import type { ReactNode } from "react";

import "./EnterpriseDataGrid.css";

export interface EnterpriseColumn<T> {
  key: string;
  header: string;
  accessor: (row: T) => ReactNode;
  sortValue?: (row: T) => string | number | null | undefined;
  width?: number;
  align?: "left" | "center" | "right";
}

interface Props<T> {
  rows: T[];
  columns: EnterpriseColumn<T>[];
  rowKey: (row: T) => string | number;
  emptyMessage?: string;
  loading?: boolean;
  quickSearch?: (row: T, query: string) => boolean;
  onRowClick?: (row: T) => void;
}

export default function EnterpriseDataGrid<T>({rows,columns,rowKey,emptyMessage="No records found.",loading=false,quickSearch,onRowClick}:Props<T>){const[query,setQuery]=useState("");const[sortKey,setSortKey]=useState<string|null>(null);const[dir,setDir]=useState<"asc"|"desc">("asc");const visible=useMemo(()=>{const q=query.trim().toLowerCase();let x=q&&quickSearch?rows.filter(r=>quickSearch(r,q)):[...rows];const c=columns.find(c=>c.key===sortKey);if(c?.sortValue)x.sort((a,b)=>{const av=c.sortValue!(a),bv=c.sortValue!(b);if(av==null)return 1;if(bv==null)return-1;const n=typeof av==="number"&&typeof bv==="number"?av-bv:String(av).localeCompare(String(bv));return dir==="asc"?n:-n});return x},[rows,columns,query,quickSearch,sortKey,dir]);function sort(c:EnterpriseColumn<T>){if(!c.sortValue)return;if(sortKey===c.key)setDir(d=>d==="asc"?"desc":"asc");else{setSortKey(c.key);setDir("asc")}}function exportCsv(){const esc=(v:unknown)=>`"${String(v??"").replaceAll('"','""')}"`;const lines=[columns.map(c=>esc(c.header)),...visible.map(r=>columns.map(c=>esc(c.sortValue?c.sortValue(r):"")))];const blob=new Blob([lines.map(l=>l.join(",")).join("\r\n")],{type:"text/csv;charset=utf-8"});const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="export.csv";a.click();URL.revokeObjectURL(url)}return <section className="enterprise-grid"><div className="enterprise-grid__toolbar"><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search this table..."/><div><span>{visible.length.toLocaleString()} rows</span><button type="button" onClick={exportCsv}>Export CSV</button></div></div><div className="enterprise-grid__viewport"><table><thead><tr>{columns.map(c=><th key={c.key} style={{width:c.width,textAlign:c.align??"left"}}><button type="button" onClick={()=>sort(c)}>{c.header}{sortKey===c.key?(dir==="asc"?" ↑":" ↓"):""}</button></th>)}</tr></thead><tbody>{loading?<tr><td colSpan={columns.length}><div className="enterprise-grid__empty">Loading records...</div></td></tr>:visible.length===0?<tr><td colSpan={columns.length}><div className="enterprise-grid__empty">{emptyMessage}</div></td></tr>:visible.map(r=><tr key={rowKey(r)} onClick={()=>onRowClick?.(r)} className={onRowClick?"clickable":""}>{columns.map(c=><td key={c.key} style={{textAlign:c.align??"left"}}>{c.accessor(r)}</td>)}</tr>)}</tbody></table></div></section>}
