"""Private SQLite state, expiry-aware resolution cache and atomic JSON snapshots."""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from urllib.parse import urlsplit, parse_qs
from .models import url_key, utc_now


def cache_expiry(url: str, now: float, maximum_age: int) -> float:
    expiry=now+maximum_age
    q=parse_qs(urlsplit(url).query)
    for key in ("expires","exp","valid_until","token_time"):
        if key in q:
            try: expiry=min(expiry,float(q[key][0])-5)
            except (ValueError,TypeError): return now
    if "X-Amz-Date" in q and "X-Amz-Expires" in q:
        try:
            created=datetime.strptime(q["X-Amz-Date"][0],"%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).timestamp()
            expiry=min(expiry,created+int(q["X-Amz-Expires"][0])-5)
        except (ValueError,TypeError): return now
    # Unknown token formats receive only the conservative maximum cache age.
    return expiry


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=".omega-",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump(value,f,indent=2,ensure_ascii=False); f.flush(); os.fsync(f.fileno())
        try: os.chmod(name,0o600)
        except OSError: pass
        os.replace(name,path)
    finally:
        if os.path.exists(name): os.unlink(name)


class Storage:
    def __init__(self,directory: str):
        self.path=Path(directory); self.conn=None; self.lock=asyncio.Lock()

    async def _call(self,fn):
        async with self.lock:
            task=asyncio.create_task(asyncio.to_thread(fn))
            try: return await asyncio.shield(task)
            except asyncio.CancelledError:
                # Finish the in-flight transaction before releasing the DB lock.
                await task
                raise

    async def open(self):
        def start():
            self.path.mkdir(parents=True,exist_ok=True)
            try: os.chmod(self.path,0o700)
            except OSError: pass
            p=self.path/"state.private.sqlite3"
            fd=os.open(p,os.O_CREAT|os.O_RDWR,0o600);os.close(fd)
            try: os.chmod(p,0o600)
            except OSError: pass
            self.conn=sqlite3.connect(p,check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA busy_timeout=5000")
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS post_state (
                    url_key TEXT PRIMARY KEY, attempts INTEGER NOT NULL, status TEXT NOT NULL,
                    updated_at TEXT NOT NULL, result_json TEXT);
                CREATE TABLE IF NOT EXISTS attempts (
                    run_id TEXT, url_key TEXT, started_at TEXT, finished_at TEXT, result_json TEXT,
                    PRIMARY KEY (run_id,url_key));
                CREATE TABLE IF NOT EXISTS resolution_cache (
                    url_key TEXT PRIMARY KEY, final_url TEXT NOT NULL, expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS dead_letter_queue (
                    id INTEGER PRIMARY KEY, run_id TEXT, url_key TEXT, reason TEXT, timestamp TEXT);
            """)
            self.conn.commit()
        await self._call(start)

    async def begin(self,run_id,url):
        def work():
            key=url_key(url);now=utc_now()
            self.conn.execute("""INSERT INTO post_state VALUES (?,1,'running',?,NULL)
                ON CONFLICT(url_key) DO UPDATE SET attempts=post_state.attempts+1,
                status='running',updated_at=excluded.updated_at,result_json=NULL""",(key,now))
            self.conn.execute("INSERT OR REPLACE INTO attempts VALUES (?,?,?,NULL,NULL)",(run_id,key,now))
            self.conn.commit()
            return self.conn.execute("SELECT attempts FROM post_state WHERE url_key=?",(key,)).fetchone()[0]
        return await self._call(work)

    async def finish(self,run_id,result):
        def work():
            key=url_key(result.post.url);now=utc_now();data=json.dumps(result.public())
            self.conn.execute("UPDATE post_state SET status=?,updated_at=?,result_json=? WHERE url_key=?",(result.status,now,data,key))
            self.conn.execute("UPDATE attempts SET finished_at=?,result_json=? WHERE run_id=? AND url_key=?",(now,data,run_id,key))
            if result.status not in {"verified","cancelled","pending"}:
                self.conn.execute("INSERT INTO dead_letter_queue(run_id,url_key,reason,timestamp) VALUES (?,?,?,?)",
                    (run_id,key,result.reason or result.status,now))
            self.conn.commit()
        await self._call(work)

    async def cache_get(self,url):
        def work():
            row=self.conn.execute("SELECT final_url,expires_at FROM resolution_cache WHERE url_key=?",(url_key(url),)).fetchone()
            if row and row[1]>time.time():return row[0]
            return None
        return await self._call(work)

    async def cache_put(self,url,final_url,max_age):
        def work():
            exp=cache_expiry(final_url,time.time(),max_age)
            if exp<=time.time():return
            self.conn.execute("INSERT OR REPLACE INTO resolution_cache VALUES (?,?,?)",(url_key(url),final_url,exp));self.conn.commit()
        await self._call(work)

    async def cache_delete(self,url):
        def work():
            self.conn.execute("DELETE FROM resolution_cache WHERE url_key=?",(url_key(url),));self.conn.commit()
        await self._call(work)

    async def snapshot(self,payload,private_streams):
        def work():
            atomic_json(self.path/"results.json",payload)
            atomic_json(self.path/"streams.private.json",private_streams)
        await self._call(work)

    async def close(self):
        if self.conn is not None:
            await self._call(self.conn.close);self.conn=None
