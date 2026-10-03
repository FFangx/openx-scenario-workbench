import { theme, type ThemeConfig } from "antd";

export const FONT = '"Inter Tight Variable", "Inter Tight", "Segoe UI", "Noto Sans SC", "Microsoft YaHei", system-ui, -apple-system, sans-serif';

/** Design tokens taken from the target comp; dark values keep the same hues. */
export function buildTheme(dark: boolean): ThemeConfig {
  return {
    algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: "#1769e0",
      colorLink: dark ? "#6aa8ff" : "#1a5fcf",
      colorSuccess: "#1f8a3e",
      colorWarning: "#d99a06",
      colorError: "#d23c3c",
      colorText: dark ? "#e3e9f0" : "#18232f",
      colorTextSecondary: dark ? "#a7b2bf" : "#5d6876",
      colorBorder: dark ? "#33414f" : "#cfd7e1",
      colorBorderSecondary: dark ? "#2a3643" : "#e2e7ee",
      colorBgContainer: dark ? "#18222d" : "#ffffff",
      colorBgLayout: dark ? "#10171f" : "#eef1f5",
      borderRadius: 4,
      fontFamily: FONT,
      fontSize: 11.5,
      controlHeight: 32,
    },
    components: {
      Table: {
        headerBg: dark ? "#1e2935" : "#f6f8fa",
        headerColor: dark ? "#cfd8e2" : "#2a3542",
        cellPaddingBlockSM: 6,
        cellPaddingInlineSM: 8,
        cellFontSizeSM: 12.5,
        rowSelectedBg: dark ? "#1c3350" : "#eaf2fe",
        rowSelectedHoverBg: dark ? "#21406a" : "#e0ecfd",
        rowHoverBg: dark ? "#1d2833" : "#f6f9fd",
      },
      Tabs: {
        itemSelectedColor: dark ? "#6aa8ff" : "#1769e0",
        inkBarColor: dark ? "#6aa8ff" : "#1769e0",
        horizontalItemPadding: "8px 2px 9px",
        horizontalItemGutter: 26,
        titleFontSize: 13.5,
        horizontalMargin: "0 0 10px 0",
      },
      Select: { controlHeight: 27, fontSize: 11.5 },
      Button: { fontWeight: 500, contentFontSize: 12, contentFontSizeLG: 13, controlHeightLG: 41 },
      Descriptions: { labelBg: dark ? "#1b2530" : "#fafbfc", itemPaddingBottom: 0 },
      Tag: { defaultBg: dark ? "#253140" : "#f3f6f9" },
    },
  };
}
