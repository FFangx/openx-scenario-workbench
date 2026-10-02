"""A narrowly scoped language adapter for Streamlit's fixed native microcopy.

Streamlit 1.64 has no file-uploader button-label or locale option. The v2
component uses documented app-page DOM privileges to translate fixed labels
and their accessible names. It never reads files, inputs, source text or state.
Unknown labels fail open; Python's business controls remain the main UI.
"""
import streamlit as st
from weakref import WeakKeyDictionary


_JS = r"""
export default function(component) {
  const {parentElement, data} = component;
  parentElement.__openxLocaleObserver?.disconnect();
  const zh = data === 'zh';
  const labels = {
    'Upload': '选择文件', 'Browse files': '选择文件',
    'file upload': '上传文件',
    'Drag and drop files here': '拖放文件到这里', 'Drag and drop file here': '拖放文件到这里',
    'Add row': '添加一行', 'Delete row': '删除行', 'Delete rows': '删除选中行',
    'Show/hide columns': '显示或隐藏列', 'Download as CSV': '下载表格（CSV）',
    'Search': '查找', 'Fullscreen': '全屏', 'Exit fullscreen': '退出全屏',
    'Open': '展开选项', 'Clear all': '清空选择', 'Increment': '增加', 'Decrement': '减少',
    'Clear selection': '清空选中行',
    'Press Enter to apply.': '按回车应用', 'Press Ctrl+Enter to apply.': '按 Ctrl+回车应用',
    'Double click to edit': '双击编辑',
    'Press Enter to submit form': '按回车提交表单', 'Press Ctrl+Enter to submit form': '按 Ctrl+回车提交表单',
    'Selected values': '已选择', 'Link to heading': '此标题的链接'
  };
  const reverse = Object.fromEntries(Object.entries(labels).map(([a,b]) => [b,a]));
  function translate(text) {
    const fixed = (zh ? labels[text] : reverse[text]);
    if (fixed) return fixed;
    const size = text.match(/^(?:Limit )?(.+?) per file$/);
    if (zh && size) return `单个文件上限 ${size[1]}`;
    const localizedSize = text.match(/^单个文件上限 (.+?)$/);
    if (!zh && localizedSize && !text.includes(' · ')) return `${localizedSize[1]} per file`;
    const limit = text.match(/^(?:Limit )?(.+?) per file [•·] (.+)$/);
    if (zh && limit) return `单个文件上限 ${limit[1]} · ${limit[2]}`;
    const localizedLimit = text.match(/^单个文件上限 (.+?) · (.+)$/);
    if (!zh && localizedLimit) return `${localizedLimit[1]} per file • ${localizedLimit[2]}`;
    if (zh && text.startsWith('Remove ')) return '移除 ' + text.slice(7);
    if (!zh && text.startsWith('移除 ')) return 'Remove ' + text.slice(3);
    return text;
  }
  const selector = [
    '[data-testid="stFileUploaderDropzone"] button',
    '[data-testid="stFileUploaderDropzoneInput"]',
    '[data-testid="stFileUploaderDropzoneInstructions"]',
    '[data-testid="stDataFrame"] button',
    '[data-testid="stSelectbox"] button', '[data-testid="stMultiSelect"] button',
    '[data-testid="stMultiSelectTagsContainer"]', 'a[aria-label="Link to heading"]',
    '[data-testid="stNumberInput"] button',
    '[data-testid="InputInstructions"]', '[role="tooltip"]'
  ].join(',');
  let frame = null;
  const observer = new MutationObserver(() => {
    if (frame === null) frame = requestAnimationFrame(() => { frame = null; apply(); });
  });
  function apply() {
    observer.disconnect();
    document.querySelectorAll(selector).forEach(root => {
      for (const el of [root, ...root.querySelectorAll('*')]) {
        for (const attr of ['aria-label', 'title']) {
          const value = el.getAttribute(attr);
          if (value && translate(value) !== value) el.setAttribute(attr, translate(value));
        }
        for (const node of el.childNodes) {
          if (node.nodeType !== Node.TEXT_NODE) continue;
          const raw = node.textContent, text = raw.trim(), translated = translate(text);
          if (translated !== text) node.textContent = raw.replace(text, translated);
        }
      }
    });
    observer.observe(document.body, {childList:true, subtree:true, characterData:true,
                                     attributes:true, attributeFilter:['aria-label','title']});
  }
  parentElement.__openxLocaleObserver = observer;
  apply();
  return () => { observer.disconnect(); if (frame !== null) cancelAnimationFrame(frame); };
}
"""

_renderers = WeakKeyDictionary()


def native_locale(language):
    # Each AppTest runtime (and each server) owns its own component registry.
    runtime = st.runtime.get_instance()
    if runtime not in _renderers:
        _renderers[runtime] = st.components.v2.component("native_locale_adapter", js=_JS)
    _renderers[runtime](data=language, key="native_locale_adapter", height=0)
