using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace AIServerDesktop
{
    internal sealed class ManagerForm : Form
    {
        private const string ProjectRoot = @"D:\AIServer";
        private const string StablePublicUrl = "https://korean-real-estate.khasbal.workers.dev";
        private readonly Label statusLabel;
        private readonly Label collectionLabel;
        private readonly TextBox logBox;
        private readonly Button startButton;
        private readonly Button stopButton;
        private readonly Button externalStartButton;
        private readonly Button externalStopButton;
        private readonly Button checkButton;
        private readonly Timer refreshTimer;
        private bool isBusy;
        private string lastCollectionSummary = "";

        public ManagerForm()
        {
            Text = "AIServer 관리";
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(680, 535);
            MinimumSize = new Size(600, 450);
            Font = new Font("Malgun Gothic", 10F);
            BackColor = Color.FromArgb(246, 248, 251);

            var title = new Label
            {
                Text = "부동산 AIServer",
                Font = new Font("Malgun Gothic", 18F, FontStyle.Bold),
                AutoSize = true,
                Location = new Point(24, 20)
            };
            Controls.Add(title);

            statusLabel = new Label
            {
                Text = "상태를 확인하는 중입니다...",
                AutoSize = false,
                Location = new Point(28, 65),
                Size = new Size(620, 30),
                Font = new Font("Malgun Gothic", 11F, FontStyle.Bold),
                ForeColor = Color.FromArgb(71, 85, 105)
            };
            Controls.Add(statusLabel);

            collectionLabel = new Label
            {
                Text = "수집 상태를 확인하는 중입니다...",
                AutoSize = false,
                Location = new Point(28, 98),
                Size = new Size(620, 52),
                Font = new Font("Malgun Gothic", 10F, FontStyle.Bold),
                ForeColor = Color.FromArgb(71, 85, 105)
            };
            Controls.Add(collectionLabel);

            AddGroupLabel("로컬 서버", new Point(28, 132));
            AddGroupLabel("외부 접속", new Point(352, 132));
            startButton = CreateButton("서버 켜기", new Point(28, 160), Color.FromArgb(22, 163, 74));
            stopButton = CreateButton("서버 끄기", new Point(190, 160), Color.FromArgb(102, 166, 112));
            externalStartButton = CreateButton("외부 접속 켜기", new Point(352, 160), Color.FromArgb(5, 150, 105));
            externalStopButton = CreateButton("외부 접속 끄기", new Point(514, 160), Color.FromArgb(83, 157, 143));
            Controls.Add(startButton);
            Controls.Add(stopButton);
            Controls.Add(externalStartButton);
            Controls.Add(externalStopButton);

            checkButton = CreateButton("상태 확인", new Point(28, 212), Color.FromArgb(37, 99, 235));
            Controls.Add(checkButton);
            var openButton = CreateButton("앱 열기", new Point(190, 212), Color.FromArgb(71, 85, 105));
            openButton.Click += delegate { OpenApp(); };
            Controls.Add(openButton);

            var resultTitle = new Label
            {
                Text = "실행 결과",
                AutoSize = true,
                Font = new Font("Malgun Gothic", 10F, FontStyle.Bold),
                Location = new Point(28, 269)
            };
            Controls.Add(resultTitle);

            logBox = new TextBox
            {
                Multiline = true,
                ReadOnly = true,
                ScrollBars = ScrollBars.Vertical,
                BackColor = Color.White,
                BorderStyle = BorderStyle.FixedSingle,
                Location = new Point(28, 295),
                Size = new Size(624, 210),
                Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right
            };
            Controls.Add(logBox);

            startButton.Click += async delegate { await StartServerAsync(); };
            stopButton.Click += async delegate { await StopServerAsync(); };
            externalStartButton.Click += async delegate { await StartExternalAsync(); };
            externalStopButton.Click += async delegate { await StopExternalAsync(); };
            checkButton.Click += async delegate { await CheckStatusAsync(true); };

            refreshTimer = new Timer { Interval = 5000 };
            refreshTimer.Tick += async delegate
            {
                if (!isBusy) await CheckStatusAsync(false);
            };
            Shown += async delegate
            {
                refreshTimer.Start();
                await CheckStatusAsync(false);
            };
            FormClosed += delegate { refreshTimer.Stop(); };
        }

        private static Button CreateButton(string text, Point location, Color color)
        {
            return new Button
            {
                Text = text,
                Location = location,
                Size = new Size(138, 42),
                FlatStyle = FlatStyle.Flat,
                BackColor = color,
                ForeColor = Color.White,
                Font = new Font("Malgun Gothic", 10F, FontStyle.Bold),
                Cursor = Cursors.Hand
            };
        }

        private void AddGroupLabel(string text, Point location)
        {
            Controls.Add(new Label
            {
                Text = text,
                AutoSize = true,
                Location = location,
                Font = new Font("Malgun Gothic", 9F, FontStyle.Bold),
                ForeColor = Color.FromArgb(71, 85, 105)
            });
        }

        private async Task StartServerAsync()
        {
            SetBusy(true);
            Append("서버 시작을 요청했습니다.");
            try
            {
                int localExit = await RunScriptAsync("start-local-server.ps1");
                if (localExit != 0) throw new InvalidOperationException("로컬 서버 시작 명령이 실패했습니다.");
                Append("로컬 서버 시작 명령 완료");
                await CheckStatusAsync(false);
            }
            catch (Exception error) { ShowFailure("서버 시작 실패", error.Message); }
            finally { SetBusy(false); }
        }

        private async Task StopServerAsync()
        {
            SetBusy(true);
            Append("서버 종료를 요청했습니다.");
            try
            {
                await RunScriptAsync("stop-local-server.ps1");
                await Task.Delay(500);
                if (await IsHealthyAsync())
                    ShowFailure("종료 확인 실패", "서버가 아직 응답하고 있습니다.");
                else
                {
                    statusLabel.Text = "● 서버 꺼짐";
                    statusLabel.ForeColor = Color.FromArgb(220, 38, 38);
                    Append("성공: 로컬 서버를 종료했습니다.");
                }
            }
            catch (Exception error) { ShowFailure("서버 종료 실패", error.Message); }
            finally { SetBusy(false); }
        }

        private async Task StartExternalAsync()
        {
            SetBusy(true);
            Append("외부 접속 연결을 요청했습니다. 주소 발급에는 시간이 걸릴 수 있습니다.");
            try
            {
                if (!await IsHealthyAsync())
                    throw new InvalidOperationException("서버가 꺼져 있습니다. 서버를 먼저 켜 주세요.");
                int exitCode = await RunScriptAsync("start-public-tunnel.ps1");
                if (exitCode != 0) throw new InvalidOperationException("외부 접속 시작 명령이 실패했습니다.");
                Append("외부 접속 연결 명령 완료");
                await CheckStatusAsync(false);
            }
            catch (Exception error) { ShowFailure("외부 접속 시작 실패", error.Message); }
            finally { SetBusy(false); }
        }

        private async Task StopExternalAsync()
        {
            SetBusy(true);
            Append("외부 접속 종료를 요청했습니다.");
            try
            {
                await RunScriptAsync("stop-public-tunnel.ps1");
                Append("성공: 외부 접속을 종료했습니다. 로컬 서버는 계속 작동합니다.");
                await CheckStatusAsync(false);
            }
            catch (Exception error) { ShowFailure("외부 접속 종료 실패", error.Message); }
            finally { SetBusy(false); }
        }

        private async Task CheckStatusAsync(bool announce)
        {
            if (announce) SetBusy(true);
            try
            {
                UpdateCollectionStatus(announce);
                bool online = await IsHealthyAsync();
                bool tunnel = IsProcessFromPidFileAlive("public-tunnel.pid");
                if (online)
                {
                    statusLabel.Text = tunnel ? "● 서버: 켜짐    ● 외부 접속: 켜짐" : "● 서버: 켜짐    ○ 외부 접속: 꺼짐";
                    statusLabel.ForeColor = Color.FromArgb(22, 163, 74);
                    if (announce)
                    {
                        Append("확인 성공: http://localhost:8787 응답 정상");
                        if (tunnel) Append("고정 외부 주소: " + StablePublicUrl);
                    }
                }
                else
                {
                    statusLabel.Text = tunnel ? "○ 서버: 꺼짐    ● 외부 접속: 켜짐(서버 응답 없음)" : "○ 서버: 꺼짐    ○ 외부 접속: 꺼짐";
                    statusLabel.ForeColor = Color.FromArgb(220, 38, 38);
                    if (announce) Append("확인 결과: 서버가 현재 응답하지 않습니다.");
                }
            }
            catch (Exception error) { ShowFailure("상태 확인 실패", error.Message); }
            finally { if (announce) SetBusy(false); }
        }

        private void UpdateCollectionStatus(bool announce)
        {
            string runPath = Path.Combine(ProjectRoot, "data", "local", "collection_state.json");
            string summary;
            Color color;

            if (File.Exists(runPath))
            {
                string json = File.ReadAllText(runPath);
                string state = JsonString(json, "state");
                string phase = JsonString(json, "phase");
                string message = JsonString(json, "message");
                string started = FormatTime(JsonString(json, "started_at"));
                string finished = FormatTime(JsonString(json, "finished_at"));
                string updated = FormatTime(JsonString(json, "updated_at"));
                int failures = CountFailures(json);

                if (state == "running")
                {
                    summary = "● 수집 진행 중 · " + (phase == "history" ? "과거 이력 수집" : "최신 자료 갱신") + "\r\n" + message + " (시작 " + started + ")";
                    color = Color.FromArgb(37, 99, 235);
                }
                else if (state == "completed" || state == "completed_with_failures")
                {
                    summary = "● 수집 완료" + (failures > 0 ? " · 재시도 대상 " + failures + "개" : "") + "\r\n" + message + " (완료 " + finished + ")";
                    color = failures > 0 ? Color.FromArgb(217, 119, 6) : Color.FromArgb(22, 163, 74);
                }
                else if (state == "quota")
                {
                    summary = "● 오늘 수집 종료 · 다운로드 한도 도달\r\n" + message + " (확인 " + finished + ")";
                    color = Color.FromArgb(217, 119, 6);
                }
                else
                {
                    summary = "● 수집 실패\r\n" + message + " (확인 " + (finished.Length > 0 ? finished : updated) + ")";
                    color = Color.FromArgb(220, 38, 38);
                }
            }
            else
            {
                string reportPath = Path.Combine(ProjectRoot, "data", "local", "status.json");
                if (File.Exists(reportPath))
                {
                    string json = File.ReadAllText(reportPath);
                    summary = "● 최근 수집 완료 · " + FormatTime(JsonString(json, "finished_at")) + "\r\n" + JsonNumber(json, "completed_jobs") + "개 작업 완료 / " + JsonNumber(json, "new_rows") + "건 추가";
                    color = Color.FromArgb(22, 163, 74);
                }
                else
                {
                    summary = "○ 수집 상태 기록이 없습니다.";
                    color = Color.FromArgb(71, 85, 105);
                }
            }

            string progress = ReadProgressSummary();
            if (progress.Length > 0) summary += "\r\n" + progress;
            collectionLabel.Text = summary;
            collectionLabel.ForeColor = color;
            if ((announce || (lastCollectionSummary.Length > 0 && lastCollectionSummary != summary)) && lastCollectionSummary != summary)
                Append("수집 상태: " + summary.Replace("\r\n", " · "));
            lastCollectionSummary = summary;
        }

        private static string ReadProgressSummary()
        {
            try
            {
                string logDir = Path.Combine(ProjectRoot, "data", "local", "logs");
                if (!Directory.Exists(logDir)) return "";
                string[] files = Directory.GetFiles(logDir, "daily-*.log");
                if (files.Length == 0) return "";
                Array.Sort(files, delegate(string left, string right)
                {
                    return File.GetLastWriteTime(right).CompareTo(File.GetLastWriteTime(left));
                });
                string[] lines = File.ReadAllLines(files[0], Encoding.UTF8);
                for (int index = lines.Length - 1; index >= 0; index--)
                {
                    string line = lines[index].Trim();
                    Match progress = Regex.Match(line, "\\[진행\\s+(?<current>[0-9]+)/(?<total>[0-9]+)\\]\\s*(?<name>.*)");
                    if (progress.Success)
                        return "진행도: " + progress.Groups["current"].Value + "/" + progress.Groups["total"].Value + " · " + progress.Groups["name"].Value;
                    if (line.Contains("[일일 작업 종료]") || line.Contains("[내일 재개]") || line.Contains("[오늘 실패 목록]"))
                        return line;
                }
            }
            catch { }
            return "";
        }

        private static string JsonString(string json, string key)
        {
            Match match = Regex.Match(json, "\\\"" + Regex.Escape(key) + "\\\"\\s*:\\s*\\\"(?<value>(?:\\\\.|[^\\\"])*)\\\"");
            return match.Success ? Regex.Unescape(match.Groups["value"].Value) : "";
        }

        private static string JsonNumber(string json, string key)
        {
            Match match = Regex.Match(json, "\\\"" + Regex.Escape(key) + "\\\"\\s*:\\s*(?<value>[0-9]+)");
            return match.Success ? match.Groups["value"].Value : "0";
        }

        private static int CountFailures(string json)
        {
            Match match = Regex.Match(json, "\\\"failures\\\"\\s*:\\s*\\[(?<items>.*?)\\]", RegexOptions.Singleline);
            return match.Success && match.Groups["items"].Value.Trim().Length > 0 ? 1 : 0;
        }

        private static string FormatTime(string raw)
        {
            DateTime value;
            return DateTime.TryParse(raw, out value) ? value.ToString("MM/dd HH:mm") : raw;
        }

        private static Task<int> RunScriptAsync(string scriptName)
        {
            return Task.Run(delegate
            {
                var info = new ProcessStartInfo
                {
                    FileName = "powershell.exe",
                    Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + Path.Combine(ProjectRoot, "scripts", scriptName) + "\"",
                    WorkingDirectory = ProjectRoot,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                };
                using (var process = Process.Start(info))
                {
                    process.StandardOutput.ReadToEnd();
                    process.StandardError.ReadToEnd();
                    process.WaitForExit();
                    return process.ExitCode;
                }
            });
        }

        private static Task<bool> IsHealthyAsync()
        {
            return Task.Run(delegate
            {
                try
                {
                    var request = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:8787/api/health");
                    request.Timeout = 3000;
                    request.ReadWriteTimeout = 3000;
                    using (var response = (HttpWebResponse)request.GetResponse())
                        return response.StatusCode == HttpStatusCode.OK;
                }
                catch { return false; }
            });
        }

        private static bool IsProcessFromPidFileAlive(string fileName)
        {
            try
            {
                string path = Path.Combine(ProjectRoot, "data", "local", "run", fileName);
                int pid;
                return File.Exists(path) && int.TryParse(File.ReadAllText(path).Trim(), out pid) && !Process.GetProcessById(pid).HasExited;
            }
            catch { return false; }
        }

        private void OpenApp()
        {
            try { Process.Start("http://localhost:8787/"); }
            catch (Exception error) { ShowFailure("브라우저 열기 실패", error.Message); }
        }

        private void SetBusy(bool busy)
        {
            isBusy = busy;
            startButton.Enabled = !busy;
            stopButton.Enabled = !busy;
            externalStartButton.Enabled = !busy;
            externalStopButton.Enabled = !busy;
            checkButton.Enabled = !busy;
            Cursor = busy ? Cursors.WaitCursor : Cursors.Default;
        }

        private void Append(string message)
        {
            if (InvokeRequired) { BeginInvoke(new Action<string>(Append), message); return; }
            logBox.AppendText("[" + DateTime.Now.ToString("HH:mm:ss") + "] " + message + Environment.NewLine);
        }

        private void ShowFailure(string title, string detail)
        {
            statusLabel.Text = "● " + title;
            statusLabel.ForeColor = Color.FromArgb(220, 38, 38);
            Append(title + ": " + detail);
        }
    }

    internal static class Program
    {
        [STAThread]
        private static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new ManagerForm());
        }
    }
}
