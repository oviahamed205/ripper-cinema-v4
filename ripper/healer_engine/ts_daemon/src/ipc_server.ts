import * as net from 'net';
import * as os from 'os';
import * as path from 'path';

export interface TelemetryPacket {
  timestamp: string;
  source: string;
  level: 'INFO' | 'WARN' | 'ERROR' | 'HEALED';
  message: string;
  metadata?: Record<string, any>;
}

export class IpcServer {
  private server: net.Server;
  private pipePath: string;
  private listeners: ((pkt: TelemetryPacket) => void)[] = [];

  constructor() {
    if (os.platform() === 'win32') {
      this.pipePath = '\\\\.\\pipe\\ripper_watchdog';
    } else {
      this.pipePath = path.join(os.tmpdir(), 'ripper_watchdog.sock');
    }

    this.server = net.createServer((socket) => {
      let buffer = '';
      socket.on('data', (data) => {
        buffer += data.toString();
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const pkt: TelemetryPacket = JSON.parse(line);
            this.broadcast(pkt);
            socket.write(JSON.stringify({ status: 'ACK', received_at: new Date().toISOString() }) + '\n');
          } catch (e) {
            socket.write(JSON.stringify({ status: 'ERR', error: String(e) }) + '\n');
          }
        }
      });
    });
  }

  public onTelemetry(cb: (pkt: TelemetryPacket) => void) {
    this.listeners.push(cb);
  }

  private broadcast(pkt: TelemetryPacket) {
    for (const listener of this.listeners) {
      try {
        listener(pkt);
      } catch (err) {
        console.error('Listener callback error:', err);
      }
    }
  }

  public start(): Promise<void> {
    return new Promise((resolve, reject) => {
      this.server.listen(this.pipePath, () => {
        console.log(`[IPC Server] Listening on ${this.pipePath}`);
        resolve();
      });
      this.server.on('error', (err) => reject(err));
    });
  }

  public stop(): Promise<void> {
    return new Promise((resolve) => {
      this.server.close(() => resolve());
    });
  }
}
