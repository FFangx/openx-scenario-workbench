"""A shared file-validation view for library assets and retrieval candidates."""
import streamlit as st
from collections import defaultdict


def validation_details(bundle, language):
    zh = language == "zh"
    with st.expander("文件标准检查" if zh else "File standard checks"):
        st.caption("按文件声明的版本检查 XML 结构；仿真可运行性需另行预览验证。" if zh else
                   "Checks XML structure against the declared version. Verify execution separately with preview.")
        labels = {"valid": "通过" if zh else "Passed", "invalid": "未通过" if zh else "Failed",
                  "unsupported": "此版本未支持" if zh else "Version unsupported",
                  "unavailable": "未完成检查" if zh else "Check unavailable"}
        for role, record in bundle.validation.items():
            title = "OpenSCENARIO" if role == "scenario" else "OpenDRIVE"
            status = record.get("status", "unavailable")
            st.write(f"{title} {record.get('version') or ''} · {labels[status]}")
            grouped = defaultdict(list)
            for issue in record.get("issues", []):
                grouped[issue["message"]].append(issue.get("line"))
            if grouped:
                count = sum(len(lines) for lines in grouped.values())
                st.warning(f"发现 {count} 处问题，归为 {len(grouped)} 类。请修复源文件后重新导入；也可先下载评估快照。" if zh else
                           f"{count} issues in {len(grouped)} groups. Fix the source files and reimport, or download an assessment snapshot.")
            if record.get("detail") or grouped:
                with st.expander("原始诊断与行号" if zh else "Original diagnostics and line numbers"):
                    if record.get("detail"):
                        st.caption(record["detail"])
                    for message, lines in grouped.items():
                        locations = ", ".join(str(line) for line in dict.fromkeys(lines) if line is not None)
                        st.write(("行 " if zh else "Lines ") + locations)
                        st.code(message, language=None)
