import sys, os, sqlite3, hashlib, secrets, threading
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QIcon, QTextCursor
from PySide6.QtWidgets import *
try:
 from google import genai
except ImportError: genai=None
try:
 import speech_recognition as sr
except ImportError: sr=None
try:
 import pyttsx3
except ImportError: pyttsx3=None

APP="CatGPT"; MODEL="gemini-3.8-flash"; KEY=os.getenv("GEMINI_API_KEY")
DB=os.path.join(os.path.expanduser("~"),"CatGPT_accounts.db")
ICON=os.path.join(os.path.dirname(os.path.abspath(__file__)),"catgpt.ico")
STYLE="QWidget{background:#080b1c;color:#eef0ff;font-family:Segoe UI} QLineEdit,QTextEdit,QListWidget,QComboBox{background:#151b35;color:white;border:1px solid #454b85;border-radius:10px;padding:9px} QPushButton{background:#6554dc;color:white;border:0;border-radius:10px;padding:10px} QPushButton:hover{background:#8274ff}"
def conn(): return sqlite3.connect(DB)
def initdb():
 with conn() as c:
  c.execute("CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY,salt TEXT NOT NULL,pw TEXT NOT NULL,avatar TEXT DEFAULT '',theme TEXT DEFAULT 'Cosmic')")
  c.execute("CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,username TEXT,role TEXT,content TEXT)")
  cols={r[1] for r in c.execute("PRAGMA table_info(users)")}
  if "avatar" not in cols:c.execute("ALTER TABLE users ADD COLUMN avatar TEXT DEFAULT ''")
  if "theme" not in cols:c.execute("ALTER TABLE users ADD COLUMN theme TEXT DEFAULT 'Cosmic'")
  c.commit()
def hp(p,s): return hashlib.pbkdf2_hmac("sha256",p.encode(),s.encode(),250000).hex()
def signup(n,p):
 n=n.strip()
 if len(n)<3 or len(p)<6:return False,"Username 3+ chars; password 6+ chars."
 s=secrets.token_hex(16)
 try:
  with conn() as c:
   c.execute("INSERT INTO users(username,salt,pw) VALUES(?,?,?)",(n,s,hp(p,s)))
   c.commit()
  return True,"Account created!"
 except sqlite3.IntegrityError:return False,"Username already exists."
 except Exception as e:return False,str(e)
def valid(n,p):
 with conn() as c:r=c.execute("SELECT salt,pw FROM users WHERE username=?",(n.strip(),)).fetchone()
 return bool(r and hp(p,r[0])==r[1])
def info(n):
 with conn() as c:return c.execute("SELECT avatar,theme FROM users WHERE username=?",(n,)).fetchone()
def hist(n):
 with conn() as c:return c.execute("SELECT role,content FROM messages WHERE username=? ORDER BY id",(n,)).fetchall()
def save(n,r,t):
 with conn() as c:
  c.execute("INSERT INTO messages(username,role,content) VALUES(?,?,?)",(n,r,t))
  c.commit()
class AI(QThread):
 chunk=Signal(str); done=Signal(str); error=Signal(str)
 def __init__(self,p,h):super().__init__();self.p=p;self.h=h
 def run(self):
  if not KEY:self.error.emit("Set GEMINI_API_KEY in CMD and restart app.");self.done.emit("");return
  if genai is None:self.error.emit("Install google-genai.");self.done.emit("");return
  try:
   client=genai.Client(api_key=KEY); contents=[{"role":"user" if r=="user" else "model","parts":[{"text":t}]} for r,t in self.h];contents.append({"role":"user","parts":[{"text":self.p}]})
   ans=""
   for x in client.models.generate_content_stream(model=MODEL,contents=contents):
    if x.text:ans+=x.text;self.chunk.emit(x.text)
   self.done.emit(ans)
  except Exception as e:self.error.emit(str(e));self.done.emit("")
class Mic(QThread):
 text=Signal(str); status=Signal(str)
 def run(self):
  if sr is None:self.status.emit("Install SpeechRecognition.");return
  try:
   r=sr.Recognizer()
   with sr.Microphone() as s:self.status.emit("Listening…");r.adjust_for_ambient_noise(s,duration=.4);a=r.listen(s,timeout=5,phrase_time_limit=12)
   self.text.emit(r.recognize_google(a))
  except Exception as e:self.status.emit(str(e))
class Login(QWidget):
 login=Signal(str,str); create=Signal(str,str)
 def __init__(self):
  super().__init__();l=QVBoxLayout(self);l.setAlignment(Qt.AlignCenter);t=QLabel("🐱 CatGPT");t.setStyleSheet("font-size:40px;color:#a99aff")
  self.n=QLineEdit();self.n.setPlaceholderText("Username");self.p=QLineEdit();self.p.setPlaceholderText("Password");self.p.setEchoMode(QLineEdit.Password)
  b=QPushButton("Login");c=QPushButton("Create account");b.clicked.connect(lambda:self.login.emit(self.n.text(),self.p.text()));c.clicked.connect(lambda:self.create.emit(self.n.text(),self.p.text()))
  for w in [t,self.n,self.p,b,c]:l.addWidget(w)
class App(QMainWindow):
 def __init__(self):
  super().__init__();self.n="";self.avatar="";self.theme="Cosmic";self.voice=True;self.busy=False
  self.setWindowTitle("CatGPT");self.resize(1050,720)
  if os.path.isfile(ICON):self.setWindowIcon(QIcon(ICON))
  self.stack=QStackedWidget();self.setCentralWidget(self.stack);self.loginpage=Login();self.loginpage.login.connect(self.login);self.loginpage.create.connect(self.create);self.stack.addWidget(self.loginpage);self.home=QWidget();self.build();self.stack.addWidget(self.home);self.setStyleSheet(STYLE);self.tray_setup()
 def build(self):
  root=QHBoxLayout(self.home);side=QVBoxLayout();title=QLabel("🐱 CatGPT");title.setStyleSheet("font-size:25px;color:#a99aff")
  self.profile=QPushButton("👤 Profile");self.settings=QPushButton("⚙ Settings");self.new=QPushButton("＋ New Chat");self.logoutb=QPushButton("Logout")
  self.list=QListWidget();self.list.addItem("Current Chat")
  for w in [title,self.profile,self.settings,self.new,QLabel("History"),self.list,self.logoutb]:side.addWidget(w)
  sw=QWidget();sw.setLayout(side);sw.setMaximumWidth(210);right=QVBoxLayout();self.welcome=QLabel("Welcome to CatGPT ✨");self.status=QLabel("Ready");self.chat=QTextEdit();self.chat.setReadOnly(True);self.input=QLineEdit();self.input.setPlaceholderText("Ask CatGPT…")
  row=QHBoxLayout();self.micb=QPushButton("🎙");self.send=QPushButton("Send");self.clear=QPushButton("Clear")
  for w in [self.input,self.micb,self.send,self.clear]:row.addWidget(w,1 if w is self.input else 0)
  for w in [self.welcome,self.status,self.chat]:right.addWidget(w)
  right.addLayout(row);rw=QWidget();rw.setLayout(right);root.addWidget(sw);root.addWidget(rw,1)
  self.send.clicked.connect(self.ask);self.input.returnPressed.connect(self.ask);self.new.clicked.connect(self.newchat);self.clear.clicked.connect(self.newchat);self.logoutb.clicked.connect(self.logout);self.profile.clicked.connect(self.profile_edit);self.settings.clicked.connect(self.settings_edit);self.micb.clicked.connect(self.listen)
 def tray_setup(self):
  self.tray=QSystemTrayIcon(self);self.tray.setIcon(QIcon(ICON) if os.path.isfile(ICON) else self.style().standardIcon(QStyle.SP_ComputerIcon));self.tray.setToolTip("CatGPT")
  menu=QMenu();a=menu.addAction("Open CatGPT");a.triggered.connect(self.restore);b=menu.addAction("Settings");b.triggered.connect(self.settings_edit);menu.addSeparator();q=menu.addAction("Quit");q.triggered.connect(self.quit);self.tray.setContextMenu(menu);self.tray.activated.connect(lambda reason:self.restore() if reason==QSystemTrayIcon.ActivationReason.Trigger else None);self.tray.show()
 def restore(self):self.showNormal();self.raise_();self.activateWindow()
 def quit(self):self.tray.hide();QApplication.quit()
 def closeEvent(self,e):e.ignore();self.hide();self.tray.show();self.tray.showMessage("CatGPT","Running in system tray. Right-click to quit.")
 def create(self,n,p):ok,m=signup(n,p);QMessageBox.information(self,"CatGPT",m)
 def login(self,n,p):
  if not valid(n,p):QMessageBox.warning(self,"Login","Incorrect username or password.");return
  self.n=n.strip();self.avatar,self.theme=info(self.n);self.load();self.welcome.setText("Welcome back, "+self.n+" ✨");self.stack.setCurrentWidget(self.home)
 def load(self):
  self.chat.clear()
  for r,t in hist(self.n):self.add(r,t,False)
 def add(self,r,t,saveit=True):
  cur=self.chat.textCursor();cur.movePosition(QTextCursor.End);name=self.n if r=="user" else "🐱 CatGPT";color="#a99aff" if r=="user" else "#69d9ff"
  safe=t.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace("\n","<br>")
  cur.insertHtml(f'<p><b style="color:{color}">{name}</b><br>{safe}</p>');cur.insertBlock();self.chat.setTextCursor(cur);self.chat.ensureCursorVisible()
  if saveit:save(self.n,r,t)
 def ask(self):
  if self.busy:return
  p=self.input.text().strip()
  if not p:return
  if not KEY:QMessageBox.warning(self,"Gemini","GEMINI_API_KEY is missing.");return
  self.input.clear();h=hist(self.n);self.add("user",p);self.busy=True;self.send.setEnabled(False);self.status.setText("Thinking…");self.answer=""
  self.ai=AI(p,h);self.ai.chunk.connect(self.stream);self.ai.done.connect(self.finish);self.ai.error.connect(lambda x:QMessageBox.warning(self,"CatGPT",x));self.ai.start()
 def stream(self,s):
  self.answer+=s;cur=self.chat.textCursor();cur.movePosition(QTextCursor.End);cur.insertText(s);self.chat.setTextCursor(cur);self.chat.ensureCursorVisible()
 def finish(self,a):
  self.busy=False;self.send.setEnabled(True);self.status.setText("Ready")
  if a.strip():save(self.n,"model",a.strip())
  if a.strip() and self.voice and pyttsx3:threading.Thread(target=self.speak,args=(a,),daemon=True).start()
 def speak(self,t):
  try:e=pyttsx3.init();e.say(t);e.runAndWait()
  except Exception:pass
 def listen(self):
  if sr is None:QMessageBox.warning(self,"Mic","Install SpeechRecognition and microphone support.");return
  self.micb.setEnabled(False);self.mic=Mic();self.mic.status.connect(self.status.setText);self.mic.text.connect(lambda t:(self.input.setText(t),self.ask()));self.mic.finished.connect(lambda:self.micb.setEnabled(True));self.mic.start()
 def newchat(self):
  if self.n:
   with conn() as c:
    c.execute("DELETE FROM messages WHERE username=?",(self.n,))
    c.commit()
   self.chat.clear();self.status.setText("New chat")
 def profile_edit(self):
  d=QDialog(self);d.setWindowTitle("Profile");f=QFormLayout(d);n=QLineEdit(self.n);preview=QLabel(os.path.basename(self.avatar) if self.avatar else "Default cat");chosen=[self.avatar]
  b=QPushButton("Choose picture")
  def pick():
   p,_=QFileDialog.getOpenFileName(self,"Select image","","Images (*.png *.jpg *.jpeg *.bmp)")
   if p:chosen[0]=p;preview.setText(os.path.basename(p))
  b.clicked.connect(pick);f.addRow("Username",n);f.addRow(preview);f.addRow(b);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);f.addRow(buttons);buttons.accepted.connect(d.accept);buttons.rejected.connect(d.reject)
  if d.exec():
   nn=n.text().strip()
   if len(nn)<3:QMessageBox.warning(self,"Profile","Username must be 3+ characters.");return
   try:
    with conn() as c:
     c.execute("UPDATE users SET username=?,avatar=? WHERE username=?",(nn,chosen[0],self.n))
     c.execute("UPDATE messages SET username=? WHERE username=?",(nn,self.n))
     c.commit()
    self.n=nn;self.avatar=chosen[0];self.welcome.setText("Welcome back, "+self.n)
   except sqlite3.IntegrityError:QMessageBox.warning(self,"Profile","Username already exists.")
 def settings_edit(self):
  d=QDialog(self);d.setWindowTitle("Settings");f=QFormLayout(d);theme=QComboBox();theme.addItems(["Cosmic","Light"]);theme.setCurrentText(self.theme);voice=QCheckBox("AI voice replies");voice.setChecked(self.voice);f.addRow("Theme",theme);f.addRow(voice);buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel);f.addRow(buttons);buttons.accepted.connect(d.accept);buttons.rejected.connect(d.reject)
  if d.exec():
   self.theme=theme.currentText();self.voice=voice.isChecked()
   self.setStyleSheet(STYLE if self.theme=="Cosmic" else "QWidget{background:#f3f4ff;color:#20243a} QLineEdit,QTextEdit{background:white;color:#20243a} QPushButton{background:#6554dc;color:white;padding:10px}")
   with conn() as c:
    c.execute("UPDATE users SET theme=? WHERE username=?",(self.theme,self.n))
    c.commit()
 def logout(self):self.n="";self.chat.clear();self.stack.setCurrentWidget(self.loginpage)
def main():
 initdb();app=QApplication(sys.argv);app.setQuitOnLastWindowClosed(False);w=App();w.show();sys.exit(app.exec())
if __name__=="__main__":main()
