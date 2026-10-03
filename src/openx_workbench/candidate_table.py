"""Theme-aware candidate selection without altering real preview pixels."""
import streamlit as st


CSS = """
.ox-candidates{max-height:280px;overflow:auto;border:1px solid var(--line,#d8e1e9);border-radius:4px;background:var(--surface,#fff);color:var(--ink-1,#10243a);font:13px/1.5 'Segoe UI',sans-serif;scrollbar-width:thin}
.ox-candidates table{width:100%;min-width:730px;border-collapse:separate;border-spacing:0;table-layout:fixed}
.ox-candidates th,.ox-candidates td{padding:7px 10px;text-align:left;vertical-align:middle;border-bottom:1px solid var(--line,#d8e1e9);border-right:1px solid var(--line,#d8e1e9);overflow-wrap:anywhere}
.ox-candidates thead th{position:sticky;top:0;z-index:1;background:var(--surface-soft,#f4f7fa);font-size:12px;font-weight:600;color:var(--muted,#526b7e)}
.ox-candidates tr:last-child td{border-bottom:0}.ox-candidates th:last-child,.ox-candidates td:last-child{border-right:0}
.ox-candidates tr.selected td{background:light-dark(#e8f2fd,#203c53)}
.ox-candidates tr.selected td:first-child{box-shadow:inset 3px 0 0 var(--accent,#0876d9)}
.ox-candidates tbody tr:hover td{background:var(--surface-soft,#f4f7fa)}
.ox-candidates td.numeric{text-align:right;font-variant-numeric:tabular-nums}
.ox-candidates button{appearance:none;border:0;background:transparent;color:var(--ink-1,#10243a);font:inherit;text-align:left;padding:4px 0;min-height:32px;width:100%;cursor:pointer}
.ox-candidates button:hover{color:var(--accent,#0876d9)}.ox-candidates button:focus-visible{outline:2px solid var(--accent,#0876d9);outline-offset:2px;border-radius:2px}
.ox-candidates button[aria-pressed=true]{font-weight:650;color:light-dark(#134e83,#a2d4ff)}
.ox-candidates img{display:block;width:64px;height:38px;object-fit:contain;border-radius:2px;background:#101922}
.ox-candidates .no-frame{font-size:11px;color:var(--muted,#526b7e)}
.ox-candidates .verdict{display:inline-block;font-size:12px;padding:3px 7px;border:1px solid var(--line,#d8e1e9);border-radius:3px;background:var(--surface-soft,#f4f7fa)}
"""

JS = """
export default function(component) {
  const {parentElement, data, setStateValue} = component;
  const host=parentElement.querySelector('.ox-candidates');
  const oldScroll=host.scrollTop;
  const table=document.createElement('table');
  table.setAttribute('aria-label',data.label);
  const cols=document.createElement('colgroup');
  [38,84,null,86,100,210].forEach(width=>{const col=document.createElement('col');if(width) col.style.width=width+'px';cols.append(col);});
  table.append(cols);
  const head=document.createElement('thead'), header=document.createElement('tr');
  data.headings.forEach(label=>{const th=document.createElement('th');th.scope='col';th.textContent=label;header.append(th);});
  head.append(header);table.append(head);
  const body=document.createElement('tbody');
  data.rows.forEach((row,index)=>{
    const tr=document.createElement('tr');
    if(index===data.selected) tr.className='selected';
    const values=[index+1,row.frame,row.title,row.score,row.cost,row.verdict];
    values.forEach((value,column)=>{
      const td=document.createElement('td');
      if(column===1){
        if(value){const img=document.createElement('img');img.src=value;img.alt=data.frameLabel+' · '+row.title;td.append(img);}
        else {const span=document.createElement('span');span.className='no-frame';span.textContent=data.noFrame;td.append(span);}
      } else if(column===2){
        const button=document.createElement('button');button.type='button';button.textContent=value;button.title=value;button.setAttribute('aria-pressed',String(index===data.selected));
        button.onclick=()=>setStateValue('selected',index);
        button.onkeydown=event=>{if(event.key==='ArrowDown'||event.key==='ArrowUp'){event.preventDefault();const next=Math.max(0,Math.min(data.rows.length-1,index+(event.key==='ArrowDown'?1:-1)));body.querySelectorAll('button')[next].focus();}};
        td.append(button);
      } else if(column===5){const badge=document.createElement('span');badge.className='verdict';badge.textContent=value;td.append(badge);}
      else{td.textContent=value??'—';if(column===0||column===3||column===4) td.className='numeric';}
      tr.append(td);
    });
    body.append(tr);
  });
  table.append(body);host.replaceChildren(table);host.scrollTop=oldScroll;
}
"""


def _renderer():
    return st.components.v2.component("openx_candidate_table", html='<div class="ox-candidates"></div>', css=CSS, js=JS)


def candidate_table(rows, selected, language, *, key):
    zh = language == "zh"
    title, score, cost, verdict, frame = ("场景", "综合", "修改成本", "决策", "真实帧") if zh else ("Scenario", "Combined", "Change cost", "Decision", "Frame")
    data = {"label": "候选资产" if zh else "Candidate assets", "selected": selected,
            "headings": ["#", frame, title, score, cost, verdict], "frameLabel": frame,
            "noFrame": "未生成" if zh else "Not captured",
            "rows": [{"title": row[title], "score": f'{row[score]:.2f}', "cost": row[cost],
                      "verdict": row[verdict], "frame": row[frame]} for row in rows]}
    state = _renderer()(data=data, key=key, default={"selected": selected}, on_selected_change=lambda: None)
    choice = state.selected
    return choice if isinstance(choice, int) and not isinstance(choice, bool) and 0 <= choice < len(rows) else selected
