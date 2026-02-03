const int N_VALVES = 2;
const int PINS[N_VALVES] = {2, 3};  // valve 1 -> D2, valve 2 -> D3
bool state[N_VALVES] = {false, false};

String line;

void apply_all() {
  for (int i = 0; i < N_VALVES; i++) {
    digitalWrite(PINS[i], state[i] ? HIGH : LOW);  // active-high MOSFET gate
  }
}

void all_off() {
  for (int i = 0; i < N_VALVES; i++) state[i] = false;
  apply_all();
}

String status_bits() {
  String s = "";
  for (int i = 0; i < N_VALVES; i++) s += (state[i] ? "1" : "0");
  return s;
}

void setup() {
  for (int i = 0; i < N_VALVES; i++) {
    pinMode(PINS[i], OUTPUT);
    digitalWrite(PINS[i], LOW);
  }
  Serial.begin(115200);
  delay(500);
  all_off();
  Serial.println("READY");
}

void handle_line(const String& cmd) {
  if (cmd == "PING") {
    Serial.println("PONG");
    return;
  }
  if (cmd == "ALL OFF") {
    all_off();
    Serial.println("OK");
    return;
  }
  if (cmd == "STATUS") {
    Serial.print("STATUS ");
    Serial.println(status_bits());
    return;
  }
  if (cmd.startsWith("VALVE ")) {
    int n = -1;
    char action[8] = {0};
    int matched = sscanf(cmd.c_str(), "VALVE %d %7s", &n, action);
    if (matched == 2 && n >= 1 && n <= N_VALVES) {
      bool on = (String(action) == "ON");
      state[n - 1] = on;
      apply_all();
      Serial.println("OK");
    } else {
      Serial.println("ERR");
    }
    return;
  }
  Serial.println("ERR");
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      line.trim();
      if (line.length() > 0) handle_line(line);
      line = "";
    } else if (c != '\r') {
      line += c;
    }
  }
}
