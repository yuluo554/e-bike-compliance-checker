"""PySide6 主窗口（M5-2）：四页签 —— 单车核查 / 批量扫描 / 跨轮对账 / 版本差异。

**零判定逻辑**：全部数据经 :mod:`ebikecheck.service` 公开函数取得；
本模块只做取数、展示与文件对话框，不做任何结论语义运算。
"""

from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..io_utils import dumps_json
from ..service import (
    ServiceError,
    check_profile,
    compare_rounds,
    export_report,
    scan_dir,
    selfcheck,
    version_diff,
    version_diff_profile,
)

#: 结论中文标签（仅展示；语义在引擎层，此处不做任何运算）。
STATE_LABELS = {
    "compliant": "符合",
    "non_compliant": "不符合",
    "not_applicable": "不适用",
    "not_provided": "未提供",
    "not_assessed": "未评估",
}
SCOPE_LABELS = {"vehicle": "整车", "battery": "电池", "charger": "充电器"}


class MainWindow(QMainWindow):
    """主窗口：四页签，每页只调 service。"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("电动自行车合规核查工作台")
        self.resize(1080, 680)
        self._status = self.statusBar()
        tabs = QTabWidget()
        tabs.addTab(CheckTab(self._report), "单车核查")
        tabs.addTab(ScanTab(self._report), "批量扫描")
        tabs.addTab(CompareTab(self._report), "跨轮对账")
        tabs.addTab(DiffTab(self._report), "版本差异")
        self.setCentralWidget(tabs)
        self._run_selfcheck_silent()

    # ---- 公共输出 ----

    def _report(self, text: str) -> None:
        """状态栏 + 摘要输出（各页签有自己的详情区）。"""
        self._status.showMessage(text[:200])

    def _run_selfcheck_silent(self) -> None:
        """启动时自检一次；失败不崩界面，把错误留给首次数操作时报。"""
        try:
            payload = selfcheck()
            self._report(
                "自检通过：规则 verified={0} / pending={1}".format(
                    payload["verified_total"], payload["pending_total"]
                )
            )
        except ServiceError as error:
            self._report("自检失败: {0}".format(error))


class _PathRow(QWidget):
    """路径选择行：输入框 + 浏览按钮（文件或目录）。"""

    def __init__(self, label: str, pick_dir: bool, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label))
        self.edit = QLineEdit()
        layout.addWidget(self.edit, stretch=1)
        button = QPushButton("浏览…")
        button.clicked.connect(lambda: self._pick(pick_dir))
        layout.addWidget(button)

    def _pick(self, pick_dir: bool) -> None:
        if pick_dir:
            path = QFileDialog.getExistingDirectory(self, "选择目录", self.edit.text() or "")
        else:
            path, _ = QFileDialog.getOpenFileName(
                self, "选择文件", self.edit.text() or "", "车型档案 (*.json)"
            )
        if path:
            self.edit.setText(path)

    def path(self) -> str:
        return self.edit.text().strip()


def _make_table(columns):
    table = QTableWidget()
    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    return table


def _fill_table(table, rows):
    table.setRowCount(0)
    for row in rows:
        index = table.rowCount()
        table.insertRow(index)
        for column, value in enumerate(row):
            table.setItem(index, column, QTableWidgetItem(str(value)))


class CheckTab(QWidget):
    """单车核查页：档案 + 可选版本 → 三维结论表 + 证据指纹 + 报告导出。"""

    def __init__(self, report):
        super().__init__()
        self._report = report
        layout = QVBoxLayout(self)

        self._profile_row = _PathRow("车型档案:", pick_dir=False)
        layout.addWidget(self._profile_row)

        form = QFormLayout()
        self._version = QComboBox()
        self._version.addItem("按日期自动锚定", None)
        self._version.addItem("GB17761-2024（当前）", "GB17761-2024")
        self._version.addItem("GB17761-2018（历史对照）", "GB17761-2018")
        form.addRow("标准版本:", self._version)
        layout.addLayout(form)

        actions = QHBoxLayout()
        check_button = QPushButton("核查")
        check_button.clicked.connect(self._on_check)
        export_button = QPushButton("导出报告（MD + XLSX）")
        export_button.clicked.connect(self._on_export)
        actions.addWidget(check_button)
        actions.addWidget(export_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self._summary = QLabel("（尚未核查）")
        layout.addWidget(self._summary)
        self._table = _make_table(["维度", "标准号", "参数", "结论", "观测值", "限值", "条款"])
        layout.addWidget(self._table, stretch=1)
        self._evidence = QPlainTextEdit()
        self._evidence.setReadOnly(True)
        self._evidence.setPlaceholderText("证据指纹（核查后填充）")
        self._evidence.setMaximumHeight(120)
        layout.addWidget(self._evidence)
        self._last_payload = None

    def _on_check(self):
        path = self._profile_row.path()
        if not path:
            QMessageBox.information(self, "提示", "请先选择车型档案 JSON")
            return
        try:
            result = check_profile(path, None, self._version.currentData())
        except ServiceError as error:
            self._last_payload = None
            QMessageBox.critical(self, "核查失败", str(error))
            return
        self._last_payload = result
        counts = result.counts()
        overall = STATE_LABELS.get(result.overall(), result.overall())
        self._summary.setText(
            "车型 {0} · 版本 {1} · 统一结论【{2}】 · 符合 {3} / 不符合 {4} / "
            "不适用 {5} / 未提供 {6}".format(
                result.profile_id, result.version_key, overall,
                counts["compliant"], counts["non_compliant"],
                counts["not_applicable"], counts["not_provided"],
            )
        )
        rows = []
        for dimension in result.dimensions:
            scope = SCOPE_LABELS.get(dimension.scope, dimension.scope)
            if not dimension.applicability.get("applicable", True):
                rows.append([scope, dimension.standard, "—（维度整体不适用）", "—", "—", "—", "—"])
                continue
            for finding in dimension.findings:
                rows.append(
                    [
                        scope,
                        finding.standard,
                        finding.param,
                        STATE_LABELS.get(finding.state, finding.state),
                        "—" if finding.observed is None else str(finding.observed),
                        "（待核对）" if finding.limit is None else "{0} {1}".format(
                            finding.limit, finding.unit
                        ).strip(),
                        finding.clause or "待核对",
                    ]
                )
        _fill_table(self._table, rows)
        try:
            from ..service import evidence_chain

            evidence = evidence_chain(result)
            self._evidence.setPlainText(
                "档案 sha256: {0}\n核查载荷 sha256: {1}".format(
                    evidence["profile_sha256"], evidence["report_sha256"]
                )
            )
        except ServiceError as error:
            self._evidence.setPlainText("证据链断言失败（拒导出）: {0}".format(error))
        self._report("核查完成: {0}（{1}）".format(result.profile_id, overall))

    def _on_export(self):
        if self._last_payload is None:
            QMessageBox.information(self, "提示", "请先核查一份档案再导出报告")
            return
        out_dir = QFileDialog.getExistingDirectory(self, "选择报告输出目录")
        if not out_dir:
            return
        try:
            from ..service import evidence_chain

            evidence_chain(self._last_payload)  # 导出前置硬门（断言失败即拒）
            payload = export_report(
                self._profile_row.path(),
                out_dir,
                None,
                self._version.currentData(),
            )
        except ServiceError as error:
            QMessageBox.critical(self, "导出失败", str(error))
            return
        QMessageBox.information(
            self,
            "导出完成",
            "Markdown: {0}\nXLSX: {1}".format(payload["markdown_path"], payload["xlsx_path"]),
        )
        self._report("报告已导出到 {0}".format(out_dir))


class ScanTab(QWidget):
    """批量扫描页：目录 → 结论分布 + 逐件结果 + 失败件隔离表。"""

    def __init__(self, report):
        super().__init__()
        self._report = report
        layout = QVBoxLayout(self)
        self._dir_row = _PathRow("档案目录:", pick_dir=True)
        layout.addWidget(self._dir_row)
        button = QPushButton("扫描")
        button.clicked.connect(self._on_scan)
        layout.addWidget(button)
        self._summary = QLabel("（尚未扫描）")
        layout.addWidget(self._summary)
        self._table = _make_table(["车型编号", "结论", "符合", "不符合", "未提供", "不适用"])
        layout.addWidget(self._table, stretch=1)
        self._failed = _make_table(["失败件", "原因码", "详情"])
        layout.addWidget(self._failed, stretch=1)

    def _on_scan(self):
        directory = self._dir_row.path()
        if not directory:
            QMessageBox.information(self, "提示", "请先选择档案目录")
            return
        try:
            payload = scan_dir(directory)
        except ServiceError as error:
            QMessageBox.critical(self, "扫描失败", str(error))
            return
        counts = payload["overall_counts"]
        self._summary.setText(
            "共 {0} 件：核查 {1} / 失败隔离 {2} · 符合 {3} / 不符合 {4} / 其他 {5}".format(
                payload["total"], len(payload["scanned"]), len(payload["failed"]),
                counts["compliant"], counts["non_compliant"], counts["other"],
            )
        )
        rows = [
            [
                item["profile_id"],
                STATE_LABELS.get(item["overall"], item["overall"]),
                item["counts"]["compliant"],
                item["counts"]["non_compliant"],
                item["counts"]["not_provided"],
                item["counts"]["not_applicable"],
            ]
            for item in payload["scanned"]
        ]
        _fill_table(self._table, rows)
        failed_rows = [
            [os.path.basename(item["path"]), item["reason"], item["detail"]]
            for item in payload["failed"]
        ]
        _fill_table(self._failed, failed_rows)
        self._report(
            "扫描完成: {0} 件（不符合 {1}）".format(payload["total"], counts["non_compliant"])
        )


class CompareTab(QWidget):
    """跨轮对账页：两轮目录 → 三集合（新增越限/已整改/持续越限）。"""

    def __init__(self, report):
        super().__init__()
        self._report = report
        layout = QVBoxLayout(self)
        self._baseline = _PathRow("上轮目录:", pick_dir=True)
        self._current = _PathRow("本轮目录:", pick_dir=True)
        layout.addWidget(self._baseline)
        layout.addWidget(self._current)
        button = QPushButton("对账")
        button.clicked.connect(self._on_compare)
        layout.addWidget(button)
        self._summary = QLabel("（尚未对账）")
        layout.addWidget(self._summary)
        self._table = _make_table(["集合", "车型编号", "参数", "结论"])
        layout.addWidget(self._table, stretch=1)

    def _on_compare(self):
        baseline = self._baseline.path()
        current = self._current.path()
        if not baseline or not current:
            QMessageBox.information(self, "提示", "请先选择上轮与本轮目录")
            return
        try:
            payload = compare_rounds(baseline, current)
        except ServiceError as error:
            QMessageBox.critical(self, "对账失败", str(error))
            return
        counts = payload["reconciliation"]["counts"]
        self._summary.setText(
            "新增越限 {0} / 已整改 {1} / 持续越限 {2}".format(
                counts["new_violation"], counts["resolved"], counts["persistent"]
            )
        )
        rows = []
        labels = {
            "new_violations": "新增越限",
            "resolved": "已整改",
            "persistent": "持续越限",
        }
        for key, label in labels.items():
            for entry in payload["reconciliation"][key]:
                rows.append([label, entry[0], entry[1], entry[2]])
        _fill_table(self._table, rows)
        self._report(
            "对账完成: 新增 {0} / 整改 {1} / 持续 {2}".format(
                counts["new_violation"], counts["resolved"], counts["persistent"]
            )
        )


class DiffTab(QWidget):
    """版本差异页：规则包 diff（静态）+ 可选同档案两版结论对照（动态）。"""

    def __init__(self, report):
        super().__init__()
        self._report = report
        layout = QVBoxLayout(self)
        self._profile_row = _PathRow("档案（可选，做两版结论对照）:", pick_dir=False)
        layout.addWidget(self._profile_row)
        button = QPushButton("对照")
        button.clicked.connect(self._on_diff)
        layout.addWidget(button)
        self._summary = QLabel("（尚未对照）")
        layout.addWidget(self._summary)
        self._table = _make_table(["参数", "差异类型", "旧版", "新版", "配对依据"])
        layout.addWidget(self._table, stretch=1)
        self._dynamic = QPlainTextEdit()
        self._dynamic.setReadOnly(True)
        self._dynamic.setPlaceholderText("同档案两版结论对照（给了档案时填充）")
        self._dynamic.setMaximumHeight(140)
        layout.addWidget(self._dynamic)

    def _on_diff(self):
        try:
            payload = version_diff()
            counts = payload["counts"]
            text = "规则包差异 {0} → {1}：新增 {2} / 放宽 {3} / 收紧 {4} / 其他 {5}".format(
                payload["old_version_key"], payload["new_version_key"],
                counts.get("added", 0), counts.get("relaxed", 0),
                counts.get("tightened", 0),
                len(payload["entries"]) - counts.get("unchanged", 0)
                - counts.get("added", 0) - counts.get("relaxed", 0) - counts.get("tightened", 0),
            )
            rows = []
            kind_labels = {
                "added": "新增", "removed": "废止", "tightened": "收紧",
                "relaxed": "放宽", "value_changed": "数值变化",
                "operator_changed": "判定方式变化", "unchanged": "不变",
            }
            for entry in payload["entries"]:
                if entry["kind"] == "unchanged":
                    continue
                rows.append(
                    [
                        entry["param"],
                        kind_labels.get(entry["kind"], entry["kind"]),
                        _side_text(entry["old_side"]),
                        _side_text(entry["new_side"]),
                        entry["pairing"],
                    ]
                )
            dynamic_text = ""
            profile_path = self._profile_row.path()
            if profile_path:
                try:
                    profiled = version_diff_profile(profile_path)
                    lines = ["同档案两版结论对照（{0} vs {1}）:".format(
                        profiled["versions"][0], profiled["versions"][-1]
                    )]
                    for scope in profiled["scopes"]:
                        for row in scope["state_changes"]:
                            lines.append(
                                "  {0}: {1} → {2}".format(
                                    row["param"], row["old_state"], row["new_state"]
                                )
                            )
                    if len(lines) == 1:
                        lines.append("  （两版结论完全一致）")
                    dynamic_text = "\n".join(lines)
                except ServiceError as error:
                    dynamic_text = "结论对照失败: {0}".format(error)
            self._dynamic.setPlainText(dynamic_text or "（未选档案：只显示规则包差异）")
        except ServiceError as error:
            QMessageBox.critical(self, "对照失败", str(error))
            return
        self._summary.setText(text)
        _fill_table(self._table, rows)
        self._report(text)


def _side_text(side) -> str:
    if not side:
        return "（无要求）"
    unit = str(side.get("unit") or "")
    text = "{0} {1}".format(side.get("op"), side.get("value"))
    return "{0} {1}".format(text, unit).strip() if unit else text


def launch() -> int:
    """GUI 入口（cli 的 ``gui`` 子命令惰性调用；不返回直到窗口关闭）。"""
    import sys

    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


__all__ = ["MainWindow", "launch", "dumps_json"]
