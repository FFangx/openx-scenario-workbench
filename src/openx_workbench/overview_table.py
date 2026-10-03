"""Sortable import history that follows the workspace color scheme."""

import streamlit as st


CSS = """
.ox-history{color:var(--ink-1,#10243a);background:var(--surface,#fff);font:13px/1.5 'Segoe UI',sans-serif;border:1px solid var(--line,#d8e1e9);border-radius:6px;overflow:hidden}
.ox-history-tools{display:flex;align-items:center;justify-content:flex-end;gap:8px;padding:8px 12px;border-bottom:1px solid var(--line,#d8e1e9);background:var(--surface-soft,#f4f7fa)}
.ox-history-tools>span{margin-right:auto;color:var(--muted,#526b7e);font-size:12px}
.ox-history input{max-width:220px;min-width:0;width:100%;padding:6px 10px;border:1px solid var(--line,#d8e1e9);border-radius:4px;background:var(--surface,#fff);color:inherit;font:inherit}
.ox-history button{border:0;background:transparent;color:inherit;cursor:pointer;font:inherit;padding:0}
.ox-history button:focus-visible,.ox-history input:focus-visible{outline:2px solid var(--accent,#0876d9);outline-offset:2px}
.ox-history-tools button{padding:6px 8px;white-space:nowrap}
.ox-history-scroll{overflow:auto;max-height:440px;scrollbar-width:thin}
.ox-history table{width:100%;min-width:800px;border-collapse:collapse;table-layout:fixed}
.ox-history th{position:sticky;top:0;background:var(--surface-soft,#f4f7fa);color:var(--muted,#526b7e);font-size:12px;font-weight:600;text-align:left}
.ox-history th,.ox-history td{padding:11px 14px;border-bottom:1px solid var(--line,#d8e1e9)}
.ox-history th button{width:100%;text-align:left;font-weight:600}
.ox-history tbody tr:last-child td{border-bottom:0}.ox-history tbody tr:hover{background:var(--surface-soft,#f4f7fa)}
.ox-history td{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ox-history td:first-child{font-weight:550}.ox-history td:nth-child(2),.ox-history td:last-child{color:var(--muted,#526b7e)}
.ox-history td:last-child,.ox-history td:nth-child(3){font-variant-numeric:tabular-nums;font-size:12px}
.ox-history th:nth-child(3),.ox-history td:nth-child(3){text-align:right}
.ox-history .status{display:inline-flex;align-items:center;gap:7px;font-size:12px}
.ox-history .status::before{content:'';width:6px;height:6px;border-radius:50%;background:var(--muted,#526b7e)}
.ox-history .status.playable{color:light-dark(#17633b,#97d8af)}.ox-history .status.playable::before{background:light-dark(#23864e,#72c793)}
.ox-history .status.failed{color:light-dark(#a82d32,#ffb3b5)}.ox-history .status.failed::before{background:currentColor}
.ox-history:fullscreen{padding:20px;background:var(--surface,#fff);overflow:auto}.ox-history:fullscreen .ox-history-scroll{max-height:none}
"""

JS = """
export default function({parentElement,data}) {
  const host=parentElement.querySelector('.ox-history');
  host.replaceChildren();
  const tools=document.createElement('div');tools.className='ox-history-tools';
  const count=document.createElement('span');tools.append(count);
  const search=document.createElement('input');search.type='search';search.placeholder=data.search;search.setAttribute('aria-label',data.search);tools.append(search);
  const fullscreen=document.createElement('button');fullscreen.type='button';fullscreen.textContent=data.fullscreen;
  fullscreen.onclick=()=>{if(document.fullscreenElement)document.exitFullscreen();else host.requestFullscreen();};tools.append(fullscreen);host.append(tools);
  const scroll=document.createElement('div');scroll.className='ox-history-scroll';host.append(scroll);
  const table=document.createElement('table');table.setAttribute('aria-label',data.label);scroll.append(table);
  const cols=document.createElement('colgroup');[44,17,7,12,20].forEach(width=>{const col=document.createElement('col');col.style.width=width+'%';cols.append(col);});table.append(cols);
  const head=document.createElement('thead'),header=document.createElement('tr');head.append(header);table.append(head);
  const body=document.createElement('tbody');table.append(body);
  let sort=-1,ascending=true;
  const collator=new Intl.Collator(data.locale,{numeric:true,sensitivity:'base'});
  const render=()=>{
    const query=search.value.trim().toLocaleLowerCase();
    const rows=data.rows.filter(row=>row.values.some(value=>String(value).toLocaleLowerCase().includes(query)));
    if(sort>=0)rows.sort((a,b)=>(ascending?1:-1)*collator.compare(String(a.values[sort]),String(b.values[sort])));
    body.replaceChildren();
    rows.forEach(row=>{const tr=document.createElement('tr');row.values.forEach((value,column)=>{
      const td=document.createElement('td');td.title=String(value);
      if(column===3){const status=document.createElement('span');status.className='status '+(row.status==='playable'?'playable':['failed','unsupported','timeout'].includes(row.status)?'failed':'');status.textContent=value;td.append(status);}
      else td.textContent=value;tr.append(td);
    });body.append(tr);});
    count.textContent=rows.length+' / '+data.rows.length+' '+data.count;
    Array.from(header.children).forEach((th,index)=>{th.setAttribute('aria-sort',index===sort?(ascending?'ascending':'descending'):'none');th.firstChild.textContent=data.headings[index]+(index===sort?(ascending?' ↑':' ↓'):'');});
    if(!rows.length){const tr=document.createElement('tr'),td=document.createElement('td');td.colSpan=data.headings.length;td.textContent=data.empty;tr.append(td);body.append(tr);}
  };
  data.headings.forEach((label,index)=>{const th=document.createElement('th');th.scope='col';const button=document.createElement('button');button.type='button';button.textContent=label;button.onclick=()=>{ascending=sort===index?!ascending:true;sort=index;render();};th.append(button);header.append(th);});
  search.oninput=render;render();
}
"""


def recent_imports_table(headings, rows, language):
    zh = language == "zh"
    renderer = st.components.v2.component("openx_import_history", html='<div class="ox-history"></div>', css=CSS, js=JS)
    renderer(data={"headings": list(headings), "rows": rows, "locale": "zh-CN" if zh else "en",
                   "label": "最近导入" if zh else "Recent imports", "search": "查找导入记录" if zh else "Find imports",
                   "count": "条记录" if zh else "records", "empty": "没有符合条件的导入记录" if zh else "No matching imports",
                   "fullscreen": "全屏" if zh else "Fullscreen"}, key="recent_imports_table")
