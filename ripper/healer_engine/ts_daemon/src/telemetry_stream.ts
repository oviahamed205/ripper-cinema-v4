import * as http from 'http';
import { TelemetryPacket } from './ipc_server';

export class TelemetryStreamer {
  private server: http.Server;
  private clients: http.ServerResponse[] = [];
  private port: number;

  constructor(port = 8799) {
    this.port = port;
    this.server = http.createServer((req, res) => {
      if (req.url === '/events') {
        res.writeHead(200, {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
          'Connection': 'keep-alive',
          'Access-Control-Allow-Origin': '*',
        });
        res.write('retry: 10000\n\n');
        this.clients.push(res);
        req.on('close', () => {
          this.clients = this.clients.filter((c) => c !== res);
        });
      } else if (req.url === '/health') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'UP', client_count: this.clients.length }));
      } else {
        res.writeHead(404);
        res.end();
      }
    });
  }

  public publish(pkt: TelemetryPacket) {
    const data = `data: ${JSON.stringify(pkt)}\n\n`;
    for (const client of this.clients) {
      client.write(data);
    }
  }

  public start(): Promise<void> {
    return new Promise((resolve) => {
      this.server.listen(this.port, () => {
        console.log(`[Telemetry Streamer] SSE live on http://127.0.0.1:${this.port}/events`);
        resolve();
      });
    });
  }

  public stop(): Promise<void> {
    return new Promise((resolve) => {
      this.server.close(() => resolve());
    });
  }
}
