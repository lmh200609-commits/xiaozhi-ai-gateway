using System;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Diagnostics;
using System.Windows.Forms;

namespace XiaozhiInstaller {
    static class Program {
        [STAThread]
        static void Main() {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);

            string defaultDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "XiaozhiGateway");

            DialogResult dr = MessageBox.Show(
                "欢迎使用 小智 AI 语音网关 v2.0 (纯净空白原装版)！\n\n" +
                "本程序将自动为您安装小智网关，并创建桌面快捷方式。\n\n" +
                "安装路径：\n" + defaultDir + "\n\n" +
                "点击【确定】开始极速安装，点击【取消】退出。",
                "小智 AI 语音网关 - 安装向导",
                MessageBoxButtons.OKCancel,
                MessageBoxIcon.Information
            );

            if (dr != DialogResult.OK) return;

            try {
                if (!Directory.Exists(defaultDir)) {
                    Directory.CreateDirectory(defaultDir);
                }

                // 提取嵌入的压缩包
                Assembly asm = Assembly.GetExecutingAssembly();
                using (Stream stream = asm.GetManifestResourceStream("payload.zip")) {
                    if (stream == null) {
                        MessageBox.Show("安装资源包未找到，请重新下载安装程序！", "安装失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
                        return;
                    }

                    string tempZip = Path.Combine(Path.GetTempPath(), "xiaozhi_temp_payload.zip");
                    using (FileStream fs = new FileStream(tempZip, FileMode.Create, FileAccess.Write)) {
                        stream.CopyTo(fs);
                    }

                    // 解压并覆盖旧文件
                    using (ZipArchive archive = ZipFile.OpenRead(tempZip)) {
                        foreach (ZipArchiveEntry entry in archive.Entries) {
                            string completeFileName = Path.Combine(defaultDir, entry.FullName);
                            string directory = Path.GetDirectoryName(completeFileName);

                            if (!Directory.Exists(directory)) {
                                Directory.CreateDirectory(directory);
                            }

                            if (!string.IsNullOrEmpty(entry.Name)) {
                                entry.ExtractToFile(completeFileName, true);
                            }
                        }
                    }

                    try { File.Delete(tempZip); } catch {}
                }

                // 定位主执行程序
                string targetExe = Path.Combine(defaultDir, "XiaozhiGateway.exe");
                if (!File.Exists(targetExe)) {
                    string subExe = Path.Combine(defaultDir, "XiaozhiGateway", "XiaozhiGateway.exe");
                    if (File.Exists(subExe)) targetExe = subExe;
                }

                // 创建桌面快捷方式
                string desktop = Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory);
                string shortcutPath = Path.Combine(desktop, "小智AI语音网关.lnk");
                CreateShortcut(shortcutPath, targetExe, Path.GetDirectoryName(targetExe));

                DialogResult runDr = MessageBox.Show(
                    "🎉 安装成功！已在您的电脑桌面生成【小智AI语音网关】图标。\n\n" +
                    "是否现在立即启动小智 AI 语音网关？",
                    "安装完成",
                    MessageBoxButtons.YesNo,
                    MessageBoxIcon.Information
                );

                if (runDr == DialogResult.Yes && File.Exists(targetExe)) {
                    ProcessStartInfo psi = new ProcessStartInfo(targetExe);
                    psi.WorkingDirectory = Path.GetDirectoryName(targetExe);
                    Process.Start(psi);
                }
            } catch (Exception ex) {
                MessageBox.Show("安装遇到问题：\n" + ex.Message, "安装提示", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            }
        }

        static void CreateShortcut(string shortcutPath, string targetPath, string workingDir) {
            try {
                Type shellType = Type.GetTypeFromProgID("WScript.Shell");
                dynamic shell = Activator.CreateInstance(shellType);
                dynamic shortcut = shell.CreateShortcut(shortcutPath);
                shortcut.TargetPath = targetPath;
                shortcut.WorkingDirectory = workingDir;
                shortcut.Description = "小智 AI 语音网关平台";
                shortcut.Save();
            } catch {}
        }
    }
}
