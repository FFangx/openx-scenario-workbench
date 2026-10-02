"""A shared file-validation view for library assets and retrieval candidates."""
import streamlit as st


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
            if record.get("detail"):
                st.caption(record["detail"])
            for issue in record.get("issues", []):
                st.warning(f"L{issue['line']}: {issue['message']}")
