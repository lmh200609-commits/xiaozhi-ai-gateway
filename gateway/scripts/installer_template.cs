using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Diagnostics;
using System.Drawing;
using System.Threading;
using System.Windows.Forms;

namespace XiaozhiInstaller {
    public class InstallerForm : Form {
        private TextBox txtPath;
        private Button btnBrowse;
        private CheckBox chkDesktop;
        private CheckBox chkLaunch;
        private ProgressBar progressBar;
        private Label lblStatus;
        private Button btnInstall;
        private Button btnCancel;

        public InstallerForm() {
            InitializeUI();
        }

        private void InitializeUI() {
            this.Text = "小智 AI 语音网关 - 安装向导 (v2.0 纯净空白版)";
            this.Size = new Size(560, 360);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.FormBorderStyle = FormBorderStyle.FixedDialog;
            this.MaximizeBox = false;
            this.MinimizeBox = true;
            this.Font = new Font("Microsoft YaHei UI", 9F, FontStyle.Regular, GraphicsUnit.Point);
            this.BackColor = Color.FromArgb(248, 249, 250);

            // 1. 顶部标题
            Label lblHeader = new Label {
                Text = "🚀 欢迎安装 小智 AI 语音网关 v2.0",
                Font = new Font("Microsoft YaHei UI", 12F, FontStyle.Bold),
                ForeColor = Color.FromArgb(33, 37, 41),
                Location = new Point(25, 20),
                AutoSize = true
            };
            this.Controls.Add(lblHeader);

            Label lblSubtitle = new Label {
                Text = "纯净空白原装交付 · 零测试数据污染 · 独立运行免装Python",
                Font = new Font("Microsoft YaHei UI", 8.5F, FontStyle.Regular),
                ForeColor = Color.FromArgb(108, 117, 125),
                Location = new Point(27, 48),
                AutoSize = true
            };
            this.Controls.Add(lblSubtitle);

            // 分割线
            Panel divider = new Panel {
                Location = new Point(25, 75),
                Size = new Size(495, 1),
                BackColor = Color.FromArgb(222, 226, 230)
            };
            this.Controls.Add(divider);

            // 2. 路径选择区域
            Label lblPathPrompt = new Label {
                Text = "目标安装路径 (可自主选择安装至任意磁盘或文件夹)：",
                ForeColor = Color.FromArgb(33, 37, 41),
                Location = new Point(25, 90),
                AutoSize = true
            };
            this.Controls.Add(lblPathPrompt);

            // 智能推荐默认路径：若有 D 盘推荐 D:\XiaozhiGateway，否则 C:\XiaozhiGateway
            string defaultPath = @"C:\XiaozhiGateway";
            if (Directory.Exists(@"D:\")) {
                defaultPath = @"D:\XiaozhiGateway";
            }

            txtPath = new TextBox {
                Text = defaultPath,
                Location = new Point(25, 115),
                Size = new Size(385, 26),
                Font = new Font("Microsoft YaHei UI", 9F)
            };
            this.Controls.Add(txtPath);

            btnBrowse = new Button {
                Text = "浏览...",
                Location = new Point(420, 113),
                Size = new Size(100, 28),
                Cursor = Cursors.Hand,
                BackColor = Color.White
            };
            btnBrowse.Click += BtnBrowse_Click;
            this.Controls.Add(btnBrowse);

            // 3. 安装选项
            chkDesktop = new CheckBox {
                Text = "在桌面创建【小智AI语音网关】快捷方式图标",
                Checked = true,
                Location = new Point(25, 155),
                AutoSize = true,
                ForeColor = Color.FromArgb(33, 37, 41)
            };
            this.Controls.Add(chkDesktop);

            chkLaunch = new CheckBox {
                Text = "安装完成后立即启动网关服务 (自动打开管理后台)",
                Checked = true,
                Location = new Point(25, 185),
                AutoSize = true,
                ForeColor = Color.FromArgb(33, 37, 41)
            };
            this.Controls.Add(chkLaunch);

            // 4. 进度条与状态文字
            progressBar = new ProgressBar {
                Location = new Point(25, 220),
                Size = new Size(495, 18),
                Style = ProgressBarStyle.Marquee,
                MarqueeAnimationSpeed = 30,
                Visible = false
            };
            this.Controls.Add(progressBar);

            lblStatus = new Label {
                Text = "准备就绪，点击下方【开始安装】即可极速部署。",
                ForeColor = Color.FromArgb(108, 117, 125),
                Location = new Point(25, 245),
                AutoSize = true
            };
            this.Controls.Add(lblStatus);

            // 5. 底部按钮
            btnInstall = new Button {
                Text = "开始安装",
                Location = new Point(315, 275),
                Size = new Size(110, 34),
                BackColor = Color.FromArgb(13, 110, 253),
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Font = new Font("Microsoft YaHei UI", 9.5F, FontStyle.Bold),
                Cursor = Cursors.Hand
            };
            btnInstall.FlatAppearance.BorderSize = 0;
            btnInstall.Click += BtnInstall_Click;
            this.Controls.Add(btnInstall);

            btnCancel = new Button {
                Text = "取消",
                Location = new Point(435, 275),
                Size = new Size(85, 34),
                BackColor = Color.White,
                FlatStyle = FlatStyle.Flat,
                Cursor = Cursors.Hand
            };
            btnCancel.FlatAppearance.BorderColor = Color.FromArgb(206, 212, 218);
            btnCancel.Click += (s, e) => this.Close();
            this.Controls.Add(btnCancel);

            this.AcceptButton = btnInstall;
            this.CancelButton = btnCancel;
        }

        private void BtnBrowse_Click(object sender, EventArgs e) {
            using (FolderBrowserDialog fbd = new FolderBrowserDialog()) {
                fbd.Description = "请选择小智 AI 语音网关的安装文件夹：";
                if (Directory.Exists(txtPath.Text.Trim())) {
                    fbd.SelectedPath = txtPath.Text.Trim();
                }
                if (fbd.ShowDialog() == DialogResult.OK) {
                    string selected = fbd.SelectedPath.Trim();
                    // 若用户选择的文件夹不是以 XiaozhiGateway 结尾，自动追加子文件夹以保持整洁
                    if (!selected.EndsWith("XiaozhiGateway", StringComparison.OrdinalIgnoreCase)) {
                        selected = Path.Combine(selected, "XiaozhiGateway");
                    }
                    txtPath.Text = selected;
                }
            }
        }

        private void BtnInstall_Click(object sender, EventArgs e) {
            string targetDir = txtPath.Text.Trim();
            if (string.IsNullOrEmpty(targetDir)) {
                MessageBox.Show("请指定有效的安装路径！", "提示", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            // 锁定界面并启动进度
            txtPath.Enabled = false;
            btnBrowse.Enabled = false;
            chkDesktop.Enabled = false;
            chkLaunch.Enabled = false;
            btnInstall.Enabled = false;
            btnCancel.Enabled = false;

            progressBar.Visible = true;
            lblStatus.ForeColor = Color.FromArgb(13, 110, 253);
            lblStatus.Text = "正在解压并部署小智网关核心组件，请稍候...";

            bool createShortcut = chkDesktop.Checked;
            bool autoLaunch = chkLaunch.Checked;

            // 后台线程异步执行安装，确保 UI 流畅无卡顿
            ThreadPool.QueueUserWorkItem(_ => {
                string errorMsg = null;
                string targetExe = null;

                try {
                    // 0. 关闭可能正在运行的旧网关实例，防止文件占用报错
                    try {
                        foreach (Process p in Process.GetProcessesByName("XiaozhiGateway")) {
                            try { p.Kill(); p.WaitForExit(2000); } catch {}
                        }
                    } catch {}

                    if (!Directory.Exists(targetDir)) {
                        Directory.CreateDirectory(targetDir);
                    }

                    // 1. 提取嵌入的压缩包
                    Assembly asm = Assembly.GetExecutingAssembly();
                    using (Stream stream = asm.GetManifestResourceStream("payload.zip")) {
                        if (stream == null) {
                            throw new Exception("内置安装资源缺失，请重新下载安装包！");
                        }

                        string tempZip = Path.Combine(Path.GetTempPath(), "xiaozhi_install_temp.zip");
                        using (FileStream fs = new FileStream(tempZip, FileMode.Create, FileAccess.Write)) {
                            stream.CopyTo(fs);
                        }

                        // 2. 解压并完整写入目标目录 (自动去重顶层目录，防止多重嵌套)
                        using (ZipArchive archive = ZipFile.OpenRead(tempZip)) {
                            foreach (ZipArchiveEntry entry in archive.Entries) {
                                string relName = entry.FullName;
                                if (relName.StartsWith("XiaozhiGateway/", StringComparison.OrdinalIgnoreCase)) {
                                    relName = relName.Substring("XiaozhiGateway/".Length);
                                } else if (relName.StartsWith("XiaozhiGateway\\", StringComparison.OrdinalIgnoreCase)) {
                                    relName = relName.Substring("XiaozhiGateway\\".Length);
                                }
                                if (string.IsNullOrEmpty(relName)) continue;

                                string destPath = Path.Combine(targetDir, relName);
                                string dir = Path.GetDirectoryName(destPath);
                                if (!Directory.Exists(dir)) {
                                    Directory.CreateDirectory(dir);
                                }
                                if (!string.IsNullOrEmpty(entry.Name)) {
                                    entry.ExtractToFile(destPath, true);
                                }
                            }
                        }

                        try { File.Delete(tempZip); } catch {}
                    }

                    // 3. 定位启动可执行文件
                    targetExe = Path.Combine(targetDir, "XiaozhiGateway.exe");
                    if (!File.Exists(targetExe)) {
                        string subExe = Path.Combine(targetDir, "XiaozhiGateway", "XiaozhiGateway.exe");
                        if (File.Exists(subExe)) targetExe = subExe;
                    }

                    // 4. 创建桌面快捷方式
                    if (createShortcut && File.Exists(targetExe)) {
                        string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                        string shortcutPath = Path.Combine(desktop, "小智AI语音网关.lnk");
                        CreateDesktopShortcut(shortcutPath, targetExe, Path.GetDirectoryName(targetExe));
                    }

                } catch (Exception ex) {
                    errorMsg = ex.Message;
                }

                // 切回主线程处理完成界面
                this.BeginInvoke(new Action(() => {
                    progressBar.Visible = false;

                    if (errorMsg != null) {
                        lblStatus.ForeColor = Color.Red;
                        lblStatus.Text = "安装遇到错误: " + errorMsg;
                        txtPath.Enabled = true;
                        btnBrowse.Enabled = true;
                        btnInstall.Enabled = true;
                        btnCancel.Enabled = true;
                        MessageBox.Show("安装失败：\n" + errorMsg, "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
                        return;
                    }

                    lblStatus.ForeColor = Color.FromArgb(25, 135, 84);
                    lblStatus.Text = "🎉 安装完成！所有服务就绪。";

                    // 启动程序
                    if (autoLaunch && File.Exists(targetExe)) {
                        try {
                            ProcessStartInfo psi = new ProcessStartInfo(targetExe) {
                                WorkingDirectory = Path.GetDirectoryName(targetExe)
                            };
                            Process.Start(psi);
                        } catch (Exception ex) {
                            MessageBox.Show("启动网关服务提示: " + ex.Message);
                        }
                    }

                    MessageBox.Show(
                        "🎉 小智 AI 语音网关 已成功安装到：\n" + targetDir + "\n\n" +
                        (createShortcut ? "桌面快捷方式【小智AI语音网关】已就绪！\n" : "") +
                        (autoLaunch ? "正在为您启动原生桌面应用程序..." : ""),
                        "安装完成",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information
                    );

                    this.Close();
                }));
            });
        }

        private static void CreateDesktopShortcut(string shortcutPath, string targetPath, string workingDir) {
            try {
                Type shellType = Type.GetTypeFromProgID("WScript.Shell");
                dynamic shell = Activator.CreateInstance(shellType);
                dynamic shortcut = shell.CreateShortcut(shortcutPath);
                shortcut.TargetPath = targetPath;
                shortcut.WorkingDirectory = workingDir;
                shortcut.Description = "小智 AI 语音网关 & 硬件服务平台";
                shortcut.Save();
            } catch {}
        }

        [STAThread]
        static void Main() {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new InstallerForm());
        }
    }
}
