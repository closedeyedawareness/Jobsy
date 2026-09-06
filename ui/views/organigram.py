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
    # Level colours come from the app's OWN map (ui/shared.LEVEL_C), not a second
    # one invented here. A level is one fact; it had two colour systems, so a
    # Senior was pink on every other page and teal on this chart.
    LCOL = {lv: pair[1] for lv, pair in LEVEL_C.items()}
    DEPT_HUES = [C["iai"], C["lhi"], C["rri"], C["ohb"], C["gold"],
                 C["primary"], C["secondary"], C["accent"]]
    _DEPTS = ["Executive", "Finance", "HR", "IT", "Engineering", "Sales",
              "Marketing", "Operations", "Warehouse", "Legal",
              "Customer Service", "Support"]
    DCOL = {d: DEPT_HUES[i % len(DEPT_HUES)] for i, d in enumerate(_DEPTS)}
    FALLBACK = C["subtle"]
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
             "dept":dept,"type":"employee","color":LCOL.get(lv, FALLBACK),"children":[]}
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
                "color":LCOL.get(r.level if r and r.matched else "", FALLBACK),"manager_id":mid,"children":[]}
        roots=[]
        for eid,n in nodes.items():
            m=n.get("manager_id")
            if m and m in nodes: nodes[m]["children"].append(n)
            else: roots.append(n)
        root=roots[0] if len(roots)==1 else {"id":"__root__","name":"Organisation","type":"root",
            "color":"#17212E","matched_title":"","level":"","dept":"","children":roots}
        return _j.dumps(root,default=str)
    dept_nodes=[{"id":f"dept-{d}","name":d,"matched_title":f"{len(m)} employees","level":"",
        "dept":d,"type":"department","color":DCOL.get(d, FALLBACK),"children":m}
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

    # The org chart is where the shape of the organisation is on screen, and in
    # these markets the shape IS the answer: "headcount" means a different unit
    # in every one of them, and every threshold in this product rests on which.
    market_panel("org_structure")

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
    # The chart is an iframe, so it cannot inherit the app's stylesheet — every
    # token has to be handed to it explicitly. That is exactly why it drifted:
    # nothing broke when the app changed palette, it just quietly stopped
    # matching.
    c_bg, c_panel, c_panel2 = C["bg"], C["surface"], C["surface2"]
    c_ink, c_muted = C["ink"], C["muted"]
    c_line2, c_primary = C["line2"], C["primary"]
    c_fallback = C["subtle"]        # the d3 fill fallback, last hardcoded hue
    font = FONT_SANS
    legend = "".join(
        f'<div class="li"><div class="ld" style="background:{pair[1]}"></div>{lv}</div>'
        for lv, pair in LEVEL_C.items()
    ) + f'<div class="li"><div class="ld" style="background:{C["subtle"]}"></div>Dept</div>'
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.8.5/d3.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
/* The chart lives INSIDE the app, so it takes the app's ground. It used to be
   a light-mode diagram -- #ECEEF0 panel, black drop-shadows, pale grey links --
   dropped into a deep-indigo page, which is why it read as a foreign object. */
body{{background:{c_bg};font-family:{font};overflow:hidden;color:{c_ink}}}
#chart{{width:100%;height:700px;position:relative}}
svg{{width:100%;height:100%}}
/* A shadow on a dark ground is a glow, not a drop. Black shadow here is just mud. */
.node rect{{rx:9;ry:9;stroke:{c_line2};stroke-width:1;cursor:pointer;transition:filter .15s,opacity .15s}}
.node rect:hover{{opacity:0.92;filter:drop-shadow(0 0 6px {c_primary}66)}}
.node text{{pointer-events:none;font-family:{font}}}
.link{{fill:none;stroke:{c_line2};stroke-width:1.4;opacity:.85}}
#tip{{position:fixed;background:{c_panel2};color:{c_ink};border:1px solid {c_line2};border-radius:10px;padding:9px 13px;font-size:12px;pointer-events:none;opacity:0;transition:opacity .15s;max-width:220px;z-index:999;box-shadow:0 6px 20px rgba(0,0,0,.45)}}
#ctrl{{position:absolute;top:10px;right:10px;display:flex;flex-direction:column;gap:6px}}
.cb{{width:32px;height:32px;background:{c_panel};border:1px solid {c_line2};color:{c_ink};border-radius:9px;font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;user-select:none;transition:background .15s,border-color .15s}}
.cb:hover{{background:{c_panel2};border-color:{c_primary}}}
#leg{{position:absolute;bottom:10px;left:10px;background:{c_panel};border:1px solid {c_line2};border-radius:11px;padding:9px 13px;font-size:11px;display:flex;gap:12px;flex-wrap:wrap;color:{c_muted}}}
.li{{display:flex;align-items:center;gap:5px}}
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
<div id="leg">{legend}</div>
</div>
<div id="tip"></div>
<script>
const D={tree_json};
const W=document.getElementById("chart").clientWidth||900,H=700;
// DX is the gap between siblings and NH the box height: at 62 against a
// 48px box carrying three lines of text, the boxes touched. 88 leaves the
// separation the eye needs to read them as separate people.
const NW=175,NH=48,DX=88,DY=235,DUR=380;
const svg=d3.select("#svg");
const g=svg.append("g");
const zoom=d3.zoom().scaleExtent([0.1,3]).on("zoom",e=>g.attr("transform",e.transform));
svg.call(zoom);
document.getElementById("zi").onclick=()=>svg.transition().call(zoom.scaleBy,1.3);
document.getElementById("zo").onclick=()=>svg.transition().call(zoom.scaleBy,0.77);
// Fit the drawn tree, rather than guessing a transform. The old initial view
// was translate(60, H/2).scale(0.9) -- a fixed offset that happens to look
// right for a small tree and puts a real organisation off the bottom of the
// frame. The chart now measures what it drew.
function fitToView(animate){{
  const b=g.node().getBBox();
  if(!b.width||!b.height) return;
  const pad=48;
  const k=Math.min((W-pad*2)/b.width,(H-pad*2)/b.height,1.25);
  const tx=(W-b.width*k)/2-b.x*k, ty=(H-b.height*k)/2-b.y*k;
  const t=d3.zoomIdentity.translate(tx,ty).scale(k);
  (animate?svg.transition().duration(400):svg).call(zoom.transform,t);
}}
document.getElementById("zr").onclick=()=>fitToView(true);
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
    .attr("fill",d=>d.data.color||"{c_fallback}").attr("opacity",0.92);
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
    if(d.data.type==="department"){{const k=(d.children||d._children||[]);return k.length===1?"1 person":k.length+" people";}}
    const t=d.data.matched_title||d.data.input_title||"";return t.length>24?t.substring(0,23)+"…":t;
  }});
  nU.select(".tog").text(d=>d._children?`▶ ${{(d._children||[]).length}}`:(d.children&&d.children.length?"▼":""));
  node.exit().transition().duration(DUR).attr("transform",()=>`translate(${{src.y}},${{src.x}})`).remove();
  nodes.forEach(d=>{{d.x0=d.x;d.y0=d.y;}});
}}
update(root);
// Fit after the first paint, once the nodes have real bounding boxes.
requestAnimationFrame(()=>fitToView(false));
</script>
</body>
</html>"""
