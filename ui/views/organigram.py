"""ui/views/organigram.py — moved verbatim out of ui/app.py on 2026-09-03."""

from __future__ import annotations

from ui.shared import *  # noqa: F401,F403


def _build_org_json(df_input, results, title_col):
    """Build dept-first tree: Company → Departments → Employees."""
    import json as _j, pandas as _pd2
    id_col  = next((c for c in ["EmployeeID","employee_id","ID"] if c in df_input.columns), None)
    mgr_col = next((c for c in ["ManagerID","manager_id","ReportsTo"] if c in df_input.columns), None)
    dept_col= next((c for c in ["Department","department","Dept","BusinessUnit"] if c in df_input.columns), None)
    fn_col  = next((c for c in ["FirstName","first_name"] if c in df_input.columns), None)
    ln_col  = next((c for c in ["LastName","last_name"]   if c in df_input.columns), None)
    LSORT={"Lead":0,"Senior":1,"Medior":2,"Junior":3}
    LCOL={"Lead":"#A87CFF","Senior":"#0E7C66","Medior":"#2B5FA6","Junior":"#B9791A"}
    DCOL={"Executive":"#17212E","Finance":"#0E7C66","HR":"#2B5FA6","IT":"#B9791A",
          "Engineering":"#0E7C66","Sales":"#A8443A","Marketing":"#A87CFF",
          "Operations":"#5A6B7A","Warehouse":"#8B6914","Legal":"#2B5FA6",
          "Customer Service":"#0E7C66","Support":"#5A6B7A"}
    def gname(row):
        if fn_col and ln_col: return (str(row.get(fn_col,""))+" "+str(row.get(ln_col,""))).strip()
        return str(row.get("Name","")).strip()
    dept_groups={}
    for idx,row in df_input.iterrows():
        eid=str(row[id_col]) if id_col else str(idx)
        dept=str(row[dept_col]).strip() if dept_col else "Other"
        name=gname(row) or eid
        it=str(row.get(title_col,"")).strip() if title_col else ""
        r=results[int(idx)] if int(idx)<len(results) else None
        mt=r.standard_title if r and r.matched else it
        lv=r.level          if r and r.matched else ""
        emp={"id":eid,"name":name,"input_title":it,"matched_title":mt,"level":lv,
             "dept":dept,"type":"employee","color":LCOL.get(lv,"#5A6B7A"),"children":[]}
        dept_groups.setdefault(dept,[]).append(emp)
    for d in dept_groups:
        dept_groups[d].sort(key=lambda x:(LSORT.get(x["level"],9),x["name"]))
    # check for real hierarchy
    use_real=False
    if mgr_col and id_col:
        all_ids=set(str(r[id_col]) for _,r in df_input.iterrows())
        mc={}
        for _,row in df_input.iterrows():
            m=str(row[mgr_col]) if _pd2.notna(row.get(mgr_col)) else None
            if m and m in all_ids: mc[m]=mc.get(m,0)+1
        if mc: use_real=(max(mc.values())/len(df_input))<0.40
    if use_real:
        nodes={}
        for idx,row in df_input.iterrows():
            eid=str(row[id_col]); mid=str(row[mgr_col]) if _pd2.notna(row.get(mgr_col)) else None
            dept=str(row[dept_col]).strip() if dept_col else "Other"; name=gname(row) or eid
            it=str(row.get(title_col,"")).strip() if title_col else ""
            r=results[int(idx)] if int(idx)<len(results) else None
            nodes[eid]={"id":eid,"name":name,"input_title":it,
                "matched_title":r.standard_title if r and r.matched else it,
                "level":r.level if r and r.matched else "","dept":dept,"type":"employee",
                "color":LCOL.get(r.level if r and r.matched else "","#5A6B7A"),"manager_id":mid,"children":[]}
        roots=[]
        for eid,n in nodes.items():
            m=n.get("manager_id")
            if m and m in nodes: nodes[m]["children"].append(n)
            else: roots.append(n)
        root=roots[0] if len(roots)==1 else {"id":"__root__","name":"Organisation","type":"root",
            "color":"#17212E","matched_title":"","level":"","dept":"","children":roots}
        return _j.dumps(root,default=str)
    dept_nodes=[{"id":f"dept-{d}","name":d,"matched_title":f"{len(m)} employees","level":"",
        "dept":d,"type":"department","color":DCOL.get(d,"#5A6B7A"),"children":m}
        for d,m in sorted(dept_groups.items())]
    return _j.dumps({"id":"__root__","name":"Organisation","type":"root","color":"#17212E",
        "matched_title":f"{len(df_input)} employees","level":"","dept":"","children":dept_nodes},default=str)


def organigram_page(catalog):
    """Interactive D3 organigram."""
    st.markdown(f'<div style="font-family:{FONT_SERIF};font-size:28px;font-weight:600;'
        f'letter-spacing:-0.02em;margin-bottom:4px">Organigram</div>'
        f'<p style="color:{C["muted"]};font-size:14px;margin-bottom:16px">'
        f'Reporting lines and hierarchy based on matched roles and seniority.</p>',
        unsafe_allow_html=True)
    results=st.session_state.get("last_results",[]); df_input=st.session_state.get("upload_df")
    title_col=st.session_state.get("upload_title_col","JobTitle")
    if not results or df_input is None:
        st.info("Upload a file and run a match on the Matching page first."); return
    try:
        tree_json=_build_org_json(df_input,results,title_col)
    except Exception as exc:
        st.error(f"Could not build org tree: {exc}"); return
    total=len(results); matched=sum(1 for r in results if r.matched)
    st.markdown(f'<div style="display:flex;gap:10px;margin-bottom:16px">'
        f'{_stat_card(total,"Employees")}{_stat_card(matched,"Matched",C["teal"])}</div>',
        unsafe_allow_html=True)
    st.caption("Tap any node to expand or collapse. Pinch or scroll to zoom. Drag to pan.")
    import streamlit.components.v1 as components
    components.html(_orgchart_html(tree_json), height=700, scrolling=True)


def _orgchart_html(tree_json):
    return f"""<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#ECEEF0;font-family:Arial,sans-serif;overflow:hidden}}
#chart{{width:100%;height:700px;position:relative}}
svg{{width:100%;height:100%}}
.node rect{{rx:8;ry:8;stroke:rgba(0,0,0,0.08);stroke-width:1;cursor:pointer;filter:drop-shadow(0 2px 6px rgba(0,0,0,0.12))}}
.node rect:hover{{opacity:0.85}}
.node text{{pointer-events:none;font-family:Arial,sans-serif}}
.link{{fill:none;stroke:#C7D1D8;stroke-width:1.5}}
#tip{{position:fixed;background:#17212E;color:#fff;border-radius:8px;padding:8px 12px;font-size:12px;pointer-events:none;opacity:0;transition:opacity .15s;max-width:200px;z-index:999}}
#ctrl{{position:absolute;top:10px;right:10px;display:flex;flex-direction:column;gap:6px}}
.cb{{width:32px;height:32px;background:#fff;border:1px solid #D9E0E5;border-radius:8px;font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;box-shadow:0 1px 4px rgba(0,0,0,0.1);user-select:none}}
#leg{{position:absolute;bottom:10px;left:10px;background:#fff;border:1px solid #D9E0E5;border-radius:10px;padding:8px 12px;font-size:11px;display:flex;gap:10px;flex-wrap:wrap}}
.li{{display:flex;align-items:center;gap:4px}}
.ld{{width:10px;height:10px;border-radius:50%}}
</style>
</head>
<body>
<div id="chart">
<svg id="svg"></svg>
<div id="ctrl">
  <div class="cb" id="zi">+</div>
  <div class="cb" id="zo">−</div>
  <div class="cb" id="zr">⌂</div>
</div>
<div id="leg">
  <div class="li"><div class="ld" style="background:#A87CFF"></div>Lead</div>
  <div class="li"><div class="ld" style="background:#0E7C66"></div>Senior</div>
  <div class="li"><div class="ld" style="background:#2B5FA6"></div>Medior</div>
  <div class="li"><div class="ld" style="background:#B9791A"></div>Junior</div>
  <div class="li"><div class="ld" style="background:#5A6B7A"></div>Dept</div>
</div>
</div>
<div id="tip"></div>
<script>
const D={tree_json};
const W=document.getElementById("chart").clientWidth||900,H=700;
const NW=175,NH=48,DX=62,DY=225,DUR=380;
const svg=d3.select("#svg");
const g=svg.append("g");
const zoom=d3.zoom().scaleExtent([0.1,3]).on("zoom",e=>g.attr("transform",e.transform));
svg.call(zoom);
document.getElementById("zi").onclick=()=>svg.transition().call(zoom.scaleBy,1.3);
document.getElementById("zo").onclick=()=>svg.transition().call(zoom.scaleBy,0.77);
document.getElementById("zr").onclick=()=>svg.transition().duration(400).call(zoom.transform,d3.zoomIdentity.translate(60,H/2).scale(0.9));
const treeFn=d3.tree().nodeSize([DX,DY]);
let root=d3.hierarchy(D,d=>d.children||[]);
root.x0=H/2; root.y0=0;
function collapse(d,md,cd){{
  if(!d.children)return;
  if(cd>=md){{d._children=d.children;d.children=null;}}
  else d.children.forEach(c=>collapse(c,md,cd+1));
}}
collapse(root,1,0);
const tip=document.getElementById("tip");
function showTip(e,d){{
  const n=d.data;
  tip.innerHTML=`<b>${{n.name||n.id}}</b><br>${{n.input_title||""}}${{n.matched_title&&n.matched_title!==n.input_title?"<br>→ "+n.matched_title:""}}${{n.level?"<br><span style='opacity:.7'>"+n.level+"</span>":""}}`;
  tip.style.opacity=1;tip.style.left=(e.clientX+10)+"px";tip.style.top=(e.clientY-10)+"px";
}}
const diag=d3.linkHorizontal().x(d=>d.y).y(d=>d.x);
function update(src){{
  treeFn(root);
  const nodes=root.descendants(),links=root.links();
  const link=g.selectAll("path.link").data(links,d=>d.target.data.id);
  const lE=link.enter().append("path").attr("class","link").attr("d",()=>{{const o={{x:src.x0,y:src.y0}};return diag({{source:o,target:o}});}});
  link.merge(lE).transition().duration(DUR).attr("d",diag);
  link.exit().transition().duration(DUR).attr("d",()=>{{const o={{x:src.x,y:src.y}};return diag({{source:o,target:o}});}}).remove();
  const node=g.selectAll("g.node").data(nodes,d=>d.data.id);
  const nE=node.enter().append("g").attr("class","node")
    .attr("transform",()=>`translate(${{src.y0}},${{src.x0}})`)
    .on("click",(e,d)=>{{if(d.children){{d._children=d.children;d.children=null;}}else if(d._children){{d.children=d._children;d._children=null;}}update(d);}})
    .on("mouseover",showTip).on("mouseout",()=>tip.style.opacity=0)
    .on("touchstart",showTip,{{passive:true}}).on("touchend",()=>tip.style.opacity=0);
  nE.append("rect").attr("x",-NW/2).attr("y",-NH/2).attr("width",NW).attr("height",NH)
    .attr("fill",d=>d.data.color||"#5A6B7A").attr("opacity",0.92);
  // dy was `type==="department" ? 5 : -8` while .sub below is always at 8, so a
  // department drew its title 3px from its subtitle and the two overlapped --
  // "Engineering" printed straight through "29 people". Departments presumably
  // once had no subtitle, where a centred title was right; they have one now.
  // Every node with a subtitle uses the same two-line offsets.
  nE.append("text").attr("dy",-8).attr("text-anchor","middle")
    .attr("fill","#fff").attr("font-size",d=>d.data.type==="department"?12:11).attr("font-weight","bold")
    .text(d=>{{const n=d.data.name||d.data.id;return n.length>20?n.substring(0,19)+"…":n;}});
  nE.append("text").attr("class","sub").attr("dy",8).attr("text-anchor","middle")
    .attr("fill","rgba(255,255,255,0.82)").attr("font-size",10);
  nE.append("text").attr("class","tog").attr("dy",NH/2-4).attr("text-anchor","middle")
    .attr("fill","rgba(255,255,255,0.6)").attr("font-size",9);
  const nU=node.merge(nE);
  nU.transition().duration(DUR).attr("transform",d=>`translate(${{d.y}},${{d.x}})`);
  nU.select(".sub").text(d=>{{
    if(d.data.type==="department"){{const k=(d.children||d._children||[]);return k.length+" people";}}
    const t=d.data.matched_title||d.data.input_title||"";return t.length>24?t.substring(0,23)+"…":t;
  }});
  nU.select(".tog").text(d=>d._children?`▶ ${{(d._children||[]).length}}`:(d.children&&d.children.length?"▼":""));
  node.exit().transition().duration(DUR).attr("transform",()=>`translate(${{src.y}},${{src.x}})`).remove();
  nodes.forEach(d=>{{d.x0=d.x;d.y0=d.y;}});
}}
update(root);
svg.call(zoom.transform,d3.zoomIdentity.translate(60,H/2).scale(0.9));
</script>
</body>
</html>"""
