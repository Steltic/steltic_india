"""Per-session job workspace: the file / RAG / activity-log tools, confined to ONE session's jobs/
directory. run_python is handled separately (it goes to the sandbox executor); everything here is a
controlled backend operation on the job files (no arbitrary code).

Path model (matches the steel contract): the session's jobs/ dir is the sandbox's /jobs mount.
  * write_file("jobs/<name>/cfg.py")  -> {session}/jobs/<name>/cfg.py
  * write_file("model.py")  [bare]    -> {session}/jobs/<active building>/model.py
  * read_file may also read engine source (read-only) so the agent can inspect the API.
"""
import json, os, re, time, hashlib, datetime, pathlib, urllib.request, urllib.error
from . import config


def _clean_name(s: str) -> str:
    return "".join(c for c in (s or "").strip() if c.isalnum() or c in "-_") or "design"


class JobWorkspace:
    def __init__(self, jobs_dir: pathlib.Path):
        self.jobs = pathlib.Path(jobs_dir).resolve()
        self.jobs.mkdir(parents=True, exist_ok=True)
        self.building = ""
        self.step = 0

    # ---------------- internals ----------------
    def _job_dir(self) -> pathlib.Path | None:
        if not self.building:
            return None
        d = self.jobs / self.building
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _resolve_write(self, path: str) -> pathlib.Path:
        norm = str(path or "").replace("\\", "/").strip()
        if not norm or norm.endswith("/") or norm.rstrip("/") in (".", "..", "jobs", "jobs/" + (self.building or "")):
            raise PermissionError(
                "write_file needs a FILE path INSIDE the job folder (e.g. 'cfg.py' or "
                "'design/calc_package.json'), not an empty path or the folder itself. Retry with a filename.")
        if norm.startswith("jobs/"):
            target = self.jobs / norm[len("jobs/"):]
        elif pathlib.Path(norm).is_absolute():
            target = pathlib.Path(norm)
        else:
            target = (self._job_dir() or self.jobs) / norm
        target = target.resolve()
        if not (target == self.jobs or self.jobs in target.parents):
            raise PermissionError("path escapes the job workspace")
        return target

    def log(self, tool: str, detail: str = "", result: str = "") -> dict:
        self.step += 1
        rec = {"step": self.step, "ts": datetime.datetime.now().isoformat(timespec="seconds"),
               "tool": tool, "detail": str(detail)[:240], "result": str(result)[:200]}
        if self.building:
            try:
                p = self.jobs / self.building / "activity_log.jsonl"
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(p, "a", encoding="utf-8") as f:
                    f.write(json.dumps(rec) + "\n")
            except Exception:
                pass                             # logging must never kill a run
        return rec

    # ---------------- tools ----------------
    def new_activity_log(self, building: str = "") -> dict:
        self.building = _clean_name(building)
        self.step = 0
        d = self.jobs / self.building
        d.mkdir(parents=True, exist_ok=True)
        try:
            (d / "activity_log.jsonl").unlink()
        except Exception:
            pass
        self.log("new_activity_log", self.building, "started")
        return {"ok": True, "building": self.building}

    def write_file(self, path: str, content: str) -> dict:
        try:
            target = self._resolve_write(path)
            if target.is_dir():
                return {"error": "write_file needs a FILE path INSIDE the job folder (e.g. 'cfg.py' or "
                                 "'design/calc_package.json'), not the folder itself ('%s' is a directory). "
                                 "Retry with a filename." % path}
            data = content if isinstance(content, str) else ("" if content is None else str(content))
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.parent / (target.name + ".tmp~")
            tmp.write_text(data, encoding="utf-8")
            os.replace(tmp, target)              # ATOMIC: a mid-write kill can never leave a truncated file
            self.log("write_file", path, f"{len(data)} bytes")
            return {"ok": True, "path": str(target.relative_to(self.jobs))}
        except PermissionError as e:
            return {"error": str(e)}
        except Exception as e:                   # NO tool exception may escape and kill the run (data loss)
            return {"error": f"write_file failed ({type(e).__name__}: {e}) -- nothing was saved; fix the "
                             "path/content and retry", "path_given": str(path)[:120]}

    def read_file(self, path: str, offset: int = 0, limit: int = 0) -> dict:
        try: off = max(int(offset or 0), 0)
        except Exception: off = 0
        try: lim = int(limit or 0)
        except Exception: lim = 0
        norm = str(path).replace("\\", "/")
        candidates = []
        if norm.startswith("jobs/"):
            candidates.append(self.jobs / norm[len("jobs/"):])
        candidates += [(self._job_dir() or self.jobs) / norm, self.jobs / norm,
                       config.STEEL_ENGINE / pathlib.Path(norm).name, config.STEEL_ENGINE / norm]
        for p in candidates:
            try:
                p = p.resolve()
                ok = (self.jobs in p.parents or p == self.jobs or config.STEEL_ENGINE in p.parents)
                if ok and p.exists() and p.is_file():
                    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                    total = len(lines)
                    end = (off + lim) if lim else min(off + 600, total)
                    sel = lines[off:end]
                    self.log("read_file", path, f"{len(sel)}/{total} lines")
                    return {"path": str(p), "total_lines": total,
                            "shown_lines": f"{off}-{off+len(sel)} of {total}",
                            "content": "\n".join(sel)[:60000]}
            except Exception:
                continue
        for p in candidates:                     # a directory is a different mistake than a missing file
            try:
                q = p.resolve()
                if (q == self.jobs or self.jobs in q.parents) and q.is_dir():
                    self.log("read_file", path, "is a directory")
                    return {"error": f"'{path}' is a DIRECTORY, not a file -- use list_files for folders, "
                                     "or read a file inside it (e.g. 'design/calc_package.json')"}
            except Exception:
                continue
        self.log("read_file", path, "not found")
        # Help the agent self-correct instead of guessing again: show what the job folder (and design/) actually hold.
        base = self._job_dir() or self.jobs
        def _ls(d):
            try: return sorted(q.name + ("/" if q.is_dir() else "") for q in d.iterdir())
            except Exception: return []
        avail = {".": _ls(base)}
        if (base / "design").is_dir(): avail["design"] = _ls(base / "design")
        return {"error": f"not found: {path}", "available": avail,
                "hint": "paths are relative to the job folder jobs/<name>/ (you are already inside it); pick a name from 'available'"}

    def list_files(self, path: str = ".") -> dict:
        norm = str(path or ".").replace("\\", "/")
        if norm.startswith("jobs/"):                       # "jobs/<name>/…" is rooted at the session jobs/ dir
            p = self.jobs / norm[len("jobs/"):]            # (matches read_file/write_file; avoids jobs/<n>/jobs/<n> doubling)
        elif norm.strip("/") == "jobs":
            p = self.jobs
        else:                                              # bare/relative -> inside the active job dir
            p = (self._job_dir() or self.jobs) / norm
        p = p.resolve()
        if not (p == self.jobs or self.jobs in p.parents):
            return {"error": "path escapes the job workspace"}
        try:
            entries = sorted(__import__("os").listdir(p))
            self.log("list_files", path, f"{len(entries)} entries")
            return {"entries": entries}
        except Exception as e:
            return {"error": str(e)}

    def activity_summary(self) -> dict:
        recs = []
        try:
            p = self.jobs / self.building / "activity_log.jsonl"
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    recs.append(json.loads(line))
        except Exception as e:
            return {"error": f"no activity log yet ({e})"}
        counts = {}
        for r in recs:
            counts[r["tool"]] = counts.get(r["tool"], 0) + 1
        return {"total_calls": len(recs), "counts_by_tool": counts, "entries": recs}

    def search_engineering_standards(self, query: str, collection: str = "engineering_standards_IS800",
                                     top_k: int = 5, clause: str = "", chapter: str = "") -> dict:
        """Search the standards corpus, ESCALATING before it is ever allowed to report nothing.

        One zero-hit answer is not evidence that a provision is absent -- it is far more often a
        filter that was too tight, a sentence sent where an id was wanted, or a document that was
        never converted on this machine. Leaving that judgement to the agent is how a design once ran
        on remembered IS values while its report said the corpus was empty. So the ladder lives
        here, in the tool, and runs whether or not the agent thinks to escalate:

          rung 1  the query exactly as asked
          rung 2  again without the clause / chapter filter, if one was set
          rung 3  as an exact-id lookup, when the query (or the clause) carries an id
          rung 4  the query reworded through the corpus's own synonym layer
          rung 5  again without the document filter -- and if THAT hits, the answer says which
                  document supplied the text, because it is not the one that was asked for

        Only when every applicable rung has come back empty is the result "not found", and even then
        it says WHICH of the three kinds of nothing it is (see `_not_found`). A transport failure is
        never a rung: an unreachable RAG still HALTs the run exactly as before, because grounding was
        promised and degrading quietly to memory mid-design is the failure we are preventing."""
        flt = (f" clause={clause}" if clause else "") + (f" chapter={chapter}" if chapter else "")
        detail = f"[{collection}] top_k={top_k}{flt}: {query}"   # the [collection] tag lets report._grounding_check count per-corpus
        # No RAG configured -> soft-disable: tell the agent once to rely on its own cited AISC
        # knowledge. But a RAG that IS configured and then becomes unreachable HALTS the run (the
        # rag_unavailable sentinel below): grounding was promised, so don't silently degrade to
        # memory mid-design -- the agent loop turns it into a paused run with a Continue button.
        RAG_HALT = {"rag_unavailable": True,
                    "message": "cannot access the RAG API, restart the RAG server then click Continue."}
        if not config.RAG_API_URL:
            self.log("search_engineering_standards", detail, "RAG disabled (not configured)")
            return {"disabled": True,
                    "message": "No engineering-standards RAG is configured (RAG_API_URL is empty). Do NOT "
                               "search again -- rely on your own knowledge of IS 800 / IS 875 / IS 1893 and cite "
                               "clauses from memory, flagging any value you are unsure of for verification."}

        spec = self._is_spec_collection(collection)   # decided from what the AGENT asked for, not from the
        trail: list = []                              # widened rungs -- rung 5 must still save to rag/<slug>.txt
        seen: set = set()

        def attempt(label: str, q: str, coll: str, cl: str = "", ch: str = ""):
            """Send one rung. -> (result | None, halt). `None` with halt=False means 'skipped,
            identical to a rung already sent'; halt=True means the server died and the run stops.

            R01: a reply whose note says the SERVER failed ("server error: ...", a traceback, a
            timeout) is not an empty answer. It is retried once; if it fails again the rung is
            recorded as errored and carries no hits, and `_not_found` reports kind server_error --
            never "genuinely absent"."""
            key = (coll, (q or "").strip().lower(), (cl or "").upper(), (ch or "").upper())
            if key in seen:
                return None, False
            seen.add(key)
            f = (f" clause={cl}" if cl else "") + (f" chapter={ch}" if ch else "")
            # The [collection] tag stays FIRST and stays the collection the AGENT asked for, even on a
            # widened rung: report._grounding_check counts per-corpus off that tag, and four attempts
            # at A341 are four pieces of grounding work done for A341 however they were phrased.
            d = f"[{collection}] {label}" + (f" as={coll or 'ALL documents'}" if coll != collection else "")
            d += f" top_k={top_k}{f}: {q}"
            out, err = self._rag_post(q, coll, cl, ch)
            if out is None:
                self.log("search_engineering_standards", d, f"RAG unavailable ({err})")
                return None, True
            retried = False
            if self._is_error_reply(out):              # R01: retry an errored rung once
                retried = True
                out, err = self._rag_post(q, coll, cl, ch)
                if out is None:
                    self.log("search_engineering_standards", d, f"RAG unavailable ({err})")
                    return None, True
            errored = self._is_error_reply(out)
            if errored:
                out = dict(out)
                out["results"] = []                    # an error payload is never a set of hits
            n = len(out.get("results") or [])
            note = str(out.get("note") or out.get("error") or "")
            trail.append({"attempt": len(trail) + 1, "how": label, "collection": coll or "(all documents)",
                          "query": q, "clause": cl, "chapter": ch, "hits": n, "note": note,
                          "error": errored, "retried": retried,
                          "not_tabulated": bool(out.get("not_tabulated"))})
            if not n:                                  # a hit is logged by finish(), which knows the saved path
                self.log("search_engineering_standards", d,
                         ("SERVER ERROR (after one retry)" if errored else "0 hits")
                         + (f" -- {note[:120]}" if note else ""))
            return out, False

        def finish(out: dict, eff_coll: str, label: str, sent_q: str = "", att: int = 0,
                   thin: bool = False) -> dict:
            """A rung hit. Hand back the hits, plus what it took to get them.

            `att` is the trail number of the rung that ANSWERED (not the number of rungs sent): the
            escalation note names that rung, and says what the first attempt actually returned."""
            att = att or len(trail)
            if len(trail) > 1:
                out["escalation"] = trail
            if att > 1 and trail:
                first = trail[0]
                said = ("a server error" if first.get("error")
                        else f"{first.get('hits', 0)} hit(s)")
                out["escalated"] = (f"Attempt 1 ({first.get('how')}) returned {said}; these hits come from "
                                    f"attempt {att} ({label}). Read 'escalation' before you cite them -- the "
                                    "wording that worked is the wording to use next time.")
            errs = [t["attempt"] for t in trail if t.get("error")]
            if errs:
                out["retrieval_errors"] = (f"attempt(s) {errs} failed with a server error (after one retry); "
                                           "they are not evidence of absence.")
            if eff_coll != collection:                 # rung 5: say which document actually answered
                self._label_widened(out, collection)
            if spec and self.building:
                return self._save_rag(query, eff_coll, out, log_collection=collection, via=label,
                                      sent_query=sent_q or query, clause=clause)
            n = len(out.get("results") or [])
            d = f"[{collection}] {label}" + (f" as={eff_coll or 'ALL documents'}" if eff_coll != collection else "")
            self.log("search_engineering_standards", d + f" top_k={top_k}: {query}", f"{n} hits")
            return out

        # R02 (L-01): rungs are ranked by CLASS, not by hit count. An exact clause / table / equation
        # hit is the answer however many records it holds -- every exact lookup in the corpus returns
        # exactly one -- so it ends the ladder at once. Below that, a filtered full-text rung is
        # accepted on ENOUGH hits; a thinner one is remembered (count is only the tie-break between
        # filtered rungs) and the ladder keeps climbing. The unfiltered rung 5 runs only when rungs
        # 1-4 all came back EMPTY, so an answer from the asked document always outranks another
        # document's text. (The first ENOUGH rule, from a nine-term query that matched one chunk
        # straddling two chapters, still holds for full text.)
        ENOUGH = 3
        best: dict = {}

        def consider(out, eff_coll: str, label: str, sent_q: str = "", cid: str = ""):
            """-> the finished result when this rung is good enough, else None (keep climbing)."""
            res = ((out or {}).get("results")) or []
            n = len(res)
            if not n:
                if out and out.get("not_tabulated"):
                    # the corpus answered: this is a tabulation gap (e.g. a town in neither annex),
                    # a definite answer that no rewording will change
                    return self._not_found(query, collection, trail)
                return None
            att = len(trail)
            if eff_coll == collection and self._is_exact_reply(out, cid):
                out["exact_match"] = True
                return finish(out, eff_coll, label, sent_q=sent_q, att=att)
            if n >= ENOUGH:
                return finish(out, eff_coll, label, sent_q=sent_q, att=att)
            if n > len(((best.get("out") or {}).get("results")) or []):
                best.update(out=out, coll=eff_coll, label=label, sent=sent_q, att=att)
            return None

        def best_or_none():
            """The thin rung we kept, once every rung has been tried."""
            if not best:
                return None
            out = best["out"]
            n = len(out.get("results") or [])
            if best["att"] == 1:
                out["thin"] = (f"Your query found only {n} hit(s) and none of the {len(trail) - 1} later "
                               "attempt(s) did better. Treat it as a lead rather than an answer -- if it does "
                               "not contain the provision, ask again with the exact printed clause id and the "
                               "words the standard itself uses.")
            else:
                out["thin"] = (f"Every attempt was thin; this is the best of {len(trail)}, from "
                               f"{best['label']} (attempt {best['att']}), with {n} hit(s). Treat it as a "
                               "lead rather than an answer -- if it does not contain the provision, ask again "
                               "with the exact printed clause id and the words the standard itself uses.")
            return finish(out, best["coll"], best["label"], sent_q=best.get("sent") or "", att=best["att"],
                          thin=True)

        # ---- rung 1: exactly what was asked for -------------------------------------------------
        out, halt = attempt("rung1 as-asked", query, collection, clause, chapter)
        if halt:
            return dict(RAG_HALT)
        done = consider(out, collection, "rung1 as-asked", cid=clause or query)
        if done is not None:
            return done
        # An unknown collection name is the agent's mistake, not a corpus gap: escalating it would
        # send four more queries to a collection the server has never heard of. Say so and stop.
        if out and "unknown collection" in str(out.get("note") or "").lower():
            self.log("search_engineering_standards", detail, "unknown collection")
            return {"results": [], "found": False, "collection": collection, "escalation": trail,
                    "note": f"UNKNOWN COLLECTION {collection!r} -- the grounding server has no such corpus, so "
                            "nothing was searched. This is a typo in your call, not an absence in the "
                            "standard. Re-issue with one of the collection names the contract lists."}

        # ---- rung 2: drop the clause / chapter filter -------------------------------------------
        # Against this hub's rag_server a clause filter falls through to full text on its own, but the
        # same API is served by vector stores where clause/chapter is a hard metadata filter and a
        # near-miss id silences the query completely. Cheap rung, real failure mode.
        if clause or chapter:
            out, halt = attempt("rung2 no-filter", query, collection)
            if halt:
                return dict(RAG_HALT)
            done = consider(out, collection, "rung2 no-filter", cid=query)
            if done is not None:
                return done

        # ---- rung 3: the exact-id lookup ---------------------------------------------------------
        # The server runs exact_equation / exact_section / exact_table itself the moment `clause` is
        # set, so all we owe it is the bare id lifted out of the engineer's sentence -- plus the
        # lettered forms of a dropped-letter id, which its own routing gate cannot reach.
        for cid in self._query_ids(query, clause, chapter):
            out, halt = attempt(f"rung3 exact-id {cid}", query, collection, cid, chapter)
            if halt:
                return dict(RAG_HALT)
            done = consider(out, collection, f"rung3 exact-id {cid}", cid=cid)
            if done is not None:
                return done

        # ---- rung 4: reword through the corpus's own alias layer ---------------------------------
        for rq in self._reworded(query):
            out, halt = attempt("rung4 alias-reworded", rq, collection, "", chapter)
            if halt:
                return dict(RAG_HALT)
            done = consider(out, collection, "rung4 alias-reworded", sent_q=rq)
            if done is not None:
                return done

        # ---- rung 5: drop the document filter ----------------------------------------------------
        # Only when rungs 1-4 found NOTHING in the asked document: a thin answer from the document
        # that governs outranks a fuller one from a document that does not. An empty collection makes
        # the server search every specification it holds; for the OpenSees and example corpora the
        # equivalent widening is the group name without its sub-collection.
        low = (collection or "").lower()
        wide = "" if spec else ("opensees" if "opensees" in low else ("examples" if "example" in low else None))
        if wide is not None and not best:
            out, halt = attempt("rung5 any-document", query, wide, "", "")
            if halt:
                return dict(RAG_HALT)
            done = consider(out, wide, "rung5 any-document")
            if done is not None:
                return done

        # ---- the ladder is exhausted ------------------------------------------------------------
        # A thin rung still beats nothing: hand back the best one, labelled as thin, rather than
        # telling the agent the provision is absent when a chunk of it was actually found.
        thin = best_or_none()
        if thin is not None:
            return thin
        # Nothing anywhere: say which kind of nothing this is.
        return self._not_found(query, collection, trail)

    # ---------------- the escalation ladder's parts ----------------
    def _rag_post(self, query: str, collection: str, clause: str = "", chapter: str = ""):
        """One rung on the wire. -> (parsed result, None) or (None, last exception).

        The two attempts are the original transport retry that absorbs a cold start; they are NOT
        part of the escalation ladder, and exhausting them means the RAG is gone rather than quiet."""
        payload = {"query": query, "collection": collection, "top_k": 5}   # fixed at 5
        if clause:  payload["clause"] = clause     # exact-clause / chapter server-side filter; only sent when set
        if chapter: payload["chapter"] = chapter
        stem = self._collection_stem(collection)
        if stem:
            payload["stem"] = stem                 # India corpus document stem (IS_800_2007, …)
            payload["doc"] = stem                  # alias some servers expect
        body = json.dumps(payload).encode()
        hdrs = {"Content-Type": "application/json"}
        if config.RAG_API_TOKEN:                   # shared-secret gate on the VM (defense in depth over the VPC rule)
            hdrs["Authorization"] = "Bearer " + config.RAG_API_TOKEN
        last_err = None
        for _attempt in range(2):                  # one retry absorbs a transient blip / cold start
            try:
                req = urllib.request.Request(config.RAG_API_URL, data=body, headers=hdrs)
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.loads(r.read())
                return (data if isinstance(data, dict) else {"results": data}), None
            except Exception as e:
                last_err = e
        return None, last_err

    # ---- R01 / R02 helpers: what a reply IS, before anyone counts its hits ----
    # A note of this shape is the SERVER failing, not the corpus answering (the 2026-09 harness
    # returned "server error: SQLite objects created in a thread ..." on every rung, and the ladder
    # reported the provisions "genuinely absent").
    _SERVER_ERR_RE = re.compile(r"server error|internal error|exception|traceback|timed? ?out|"
                                r"sqlite objects|operationalerror|programmingerror|database is locked", re.I)

    def _is_error_reply(self, out) -> bool:
        """True when a reply reports a server / transport failure instead of an answer."""
        if not isinstance(out, dict):
            return False
        if out.get("results"):
            return False                       # hits are hits, whatever the note says
        if out.get("error"):
            return True
        return bool(self._SERVER_ERR_RE.search(str(out.get("note") or "")))

    @staticmethod
    def _norm_id(s) -> str:
        """'Table 10' / 'table10' / '10' -> '10'; 'Eq. 7-1' -> '7-1'; '7.3.6.' -> '7.3.6'."""
        t = str(s or "").strip()
        t = re.sub(r"^\s*(?:table|tab\.?|tbl\.?|section|sec\.?|clause|cl\.?|§|equation|eqn?\.?)\s*", "", t,
                   flags=re.I)
        return re.sub(r"\s+", "", t).rstrip(".").casefold()

    def _is_exact_reply(self, out, cid: str = "") -> bool:
        """R02: the reply IS the exact record asked for.

        Recognised when the server says so (`matched`, or the result `type` it actually ran, as
        exact_section / exact_table / exact_equation), or when a hit's section / table / equation id
        equals the id asked for. The id test is what makes an older adapter's replies count: it maps
        a table hit's `section` to the clause that cites the table, so `table_id` is compared too."""
        if not isinstance(out, dict):
            return False
        res = out.get("results") or []
        if not res:
            return False
        if str(out.get("matched") or "").lower().startswith("exact_"):
            return True
        if str(out.get("type") or "").lower().startswith("exact_") and out.get("found") is not False:
            return True
        want = self._norm_id(cid)
        if not want or len(str(cid).split()) > 3:
            return False                       # a sentence is not an id
        for h in res:
            if not isinstance(h, dict):
                continue
            for k in ("section", "section_id", "table_id", "eq_id", "clause"):
                v = h.get(k)
                if v not in (None, "") and self._norm_id(v) == want:
                    return True
        return False

    def _label_widened(self, out: dict, collection: str) -> None:
        """Rung 5 answered. Put the asked document's own hits first; say "FOUND ONLY WITHOUT THE
        DOCUMENT FILTER" only when NO hit comes from the document that was asked for."""
        res = [h for h in (out.get("results") or [])]
        stem = self._collection_stem(collection) or ""
        mine = {x.lower() for x in (stem, collection) if x}

        def src(h):
            return str(h.get("source") or h.get("doc") or "").strip() if isinstance(h, dict) else ""

        own = [h for h in res if src(h).lower() in mine]
        others = [h for h in res if src(h).lower() not in mine]
        srcs = []
        for h in others:
            s_ = src(h)
            if s_ and s_ not in srcs:
                srcs.append(s_)
        if out.get("note"):
            out["server_note"] = out["note"]
        if own:
            out["results"] = own + others
            out["also_found_in"] = srcs
            out["note"] = (f"Hits 1-{len(own)} are from {stem or collection} (found once the document filter was "
                           "dropped)" + (f"; the text is also found in: {', '.join(srcs)}" if srcs else "")
                           + ". Cite the document that actually supplied each hit.")
        else:
            out["found_in_documents"] = srcs
            out["note"] = ("FOUND ONLY WITHOUT THE DOCUMENT FILTER -- this text is from "
                           + (", ".join(srcs) or "another document in the corpus")
                           + f", NOT from {collection}. Cite the document that actually supplied it, and "
                             "confirm that document governs this member before you use the value.")

    # rag_server._EQ: the server only routes a `clause` to the EQUATION index when it has a leading
    # letter. A dropped-letter id ("3-1", "1.3.1.1-1") therefore never gets there, which is the one
    # gap in its exact-id handling that rung 3 has to close. Keep in sync with the hub's rag_server.
    _SERVER_EQ_RE = re.compile(r"^[A-Z]{1,2}\d+(?:\.\d+)*-\d+[a-z]?$", re.I)
    # Document names carry digit-hyphen pairs ("360-22", "S100-16", "7-22") shaped exactly like
    # equation ids; strip them before hunting for the id the engineer actually meant.
    _DOCNAME_RE = re.compile(r"\b(?:IS|BIS|AISC|AISI|ASCE(?:/SEI)?|ANSI)\s*/?\s*[A-Z]?\d+(?:[-–:]\d+)?(?:\s*Part\s*\d+)?\b", re.I)
    _QUERY_ID_RE = re.compile(r"\b(?:[A-Za-z]{1,2}\d+(?:\.\d+)*(?:-\d+[a-z]?)?"   # F2 - F2.2 - F2-1 - E1.3.1.1-1
                              r"|\d+\.\d+(?:\.\d+)*(?:-\d+[a-z]?)?"               # 12.8.1 - 12.8-3 - 1.3.1.1-1
                              r"|\d+-\d+[a-z]?)\b")                               # 3-1 (dropped leading letter)

    # NEW-7: unit tokens and material grades are not clause ids ("Steel 78.5 kN/m3" once sent M3).
    _UNIT_RE = re.compile(r"(?:(?<![\d.])\d+(?:\.\d+)?\s*(?:k?N|kgf?|t|g|mm|cm|m|km|[kKMG]?Pa|%|°)"
                          r"(?:\s*/\s*(?:mm|cm|m|s|h)\s*[234\u00b2\u00b3\u2074]?)?(?![A-Za-z0-9])"
                          r"|\b(?:k?N|kgf?|t|g)\s*/\s*(?:mm|cm|m)\s*[234\u00b2\u00b3\u2074]?(?![A-Za-z0-9])"
                          r"|\b(?:mm|cm|m)\s*[234\u00b2\u00b3\u2074](?![A-Za-z0-9])"
                          r"|\b(?:m|km)\s*/\s*(?:s|h)\b|\b[kKMG]?Pa\b)")
    # IS clause / annex ids are upper-case (D-1, E-1.1, F2 in AISC); a lower-case lead is a symbol
    # (k2, m3, h0) and E250 / Fe410 are steel grades.
    _NOT_AN_ID_RE = re.compile(r"^(?:[a-z]\w*|E\d{3}\w*|Fe\d{3}\w*)$")

    def _query_ids(self, query: str, clause: str = "", chapter: str = "", limit: int = 3) -> list:
        """Ids worth re-sending as an exact `clause`, most promising first.

        Two jobs, neither of which the server can do for us. One: pull the id out of a prose query --
        an agent that asks "AISC 360-22 Equation F2-1 for compact I-shapes" never sets `clause`, so
        the server only ever full-text searches a sentence. Two: expand a dropped-letter id through
        the corpus's eq_id_aliases, because the server's routing gate wants a leading letter and
        "1.3.1.1-1" does not have one."""
        cands = []
        src = (clause or "").strip()
        if src:
            cands.append(src)
        else:
            stripped = self._DOCNAME_RE.sub(" ", query or "")
            stripped = self._UNIT_RE.sub(" ", stripped)      # "kN/m3" is a unit, not clause M3
            found = [m.group(0) for m in self._QUERY_ID_RE.finditer(stripped)
                     if not self._NOT_AN_ID_RE.match(m.group(0))]
            lettered = [f for f in found if f[:1].isalpha()]
            # IS annex clause ids (D-1, E-1.1) and printed table ids ("Table 10") are exact ids too
            annex = [m.group(0) for m in re.finditer(r"\b[A-H]-\d+(?:\.\d+)*\b", stripped)]
            tables = ["Table " + m.group(1) for m in
                      re.finditer(r"\bTable\s+(\d+[A-Za-z]?(?:\s*\([a-z]\))?)", stripped, re.I)]
            cands += ((lettered or found)[:2] + annex[:1] + tables[:1])
        eq = (self._corpus_aliases().get("eq_id_aliases") or {})
        ch = (chapter or "").strip().upper()[:1]
        out = []
        for c in cands:
            c = c.strip()
            c = ("Table " + c[6:].strip()) if c.lower().startswith("table ") else c.upper()
            if not c:
                continue
            if c not in out and not (clause and c == clause.strip().upper()):
                out.append(c)                      # a clause the agent already sent was tried at rung 1
            if self._SERVER_EQ_RE.match(c):
                continue                           # the server reaches the equation index unaided
            alts = eq.get(c) or eq.get(c.lower()) or []
            # prefer the chapter the agent named: "3-1" in chapter E means E3-1, not B3-1
            for a in sorted((str(x) for x in alts), key=lambda s: (not s.upper().startswith(ch) if ch else False)):
                a = a.upper()
                if a not in out and not a.startswith("C-"):    # never alias a standard id to commentary
                    out.append(a)
        return out[:limit]

    _aliases_cache = None

    def _corpus_aliases(self) -> dict:
        """The corpus's own alias layer (indexes/aliases.json), when this machine has it.

        It ships with the Query file manager module, not with us: in a hub install DATA_DIR is
        <data>/modules_data/steltic, so the QFM workspace sits two levels up. RAG_ALIASES_FILE
        overrides that for any other layout. When it is absent the rewording rung simply does not
        fire -- we deliberately do NOT carry a second copy of the synonym table, because a copy would
        drift from the corpus it is meant to describe and start suggesting terms nothing was indexed
        under."""
        if self._aliases_cache is not None:
            return self._aliases_cache
        cands = []
        if getattr(config, "RAG_ALIASES_FILE", ""):
            cands.append(pathlib.Path(config.RAG_ALIASES_FILE))
        try:
            qfm = config.DATA.parent.parent / "grokbot"
            cands += [qfm / "indexes" / "aliases.json",
                      qfm / "engineering_rag_phase2" / "indexes" / "aliases.json"]
            # India HR: the India corpus aliases (INDIA_CORPUS_ROOT, else a sibling checkout, else
            # /workspace/engineering_rag_india -- see india_collections.india_corpus_root)
            from .india_collections import india_corpus_root
            _root = pathlib.Path(india_corpus_root())
            cands += [_root / "indexes" / "aliases.json", _root / "scripts" / "aliases.json"]
        except Exception:
            pass
        self._aliases_cache = {}
        for p in cands:
            try:
                if p.is_file():
                    d = json.loads(p.read_text(encoding="utf-8"))
                    if isinstance(d, dict):
                        self._aliases_cache = d
                        break
            except Exception:
                continue
        return self._aliases_cache

    def _reworded(self, query: str, limit: int = 2) -> list:
        """The query with a MULTI-WORD synonym swapped for the corpus's other spellings of it.

        The server already expands aliases for full-text search, but only two ways: the whole query
        when the whole query IS an alias, and single abbreviation-shaped tokens inside it. Neither
        can see a spelled-out phrase sitting mid-sentence -- "...capacity for lateral torsional
        buckling of a compact shape..." -- which is how an engineer actually writes. Swapping that
        phrase for the group's other spellings is the part of the alias layer left for us, so this
        deliberately ignores single-word and abbreviation members: re-sending those would be the
        server's own expansion a second time."""
        groups = (self._corpus_aliases().get("synonym_groups") or [])
        low = (query or "").lower()
        out = []

        def bounded(m: str):
            # R04: whole words only -- "load combination" must not match inside "load combinations"
            return re.compile(r"(?<![A-Za-z0-9])" + re.escape(m) + r"(?![A-Za-z0-9])", re.I)

        for g in groups:
            if not isinstance(g, list) or len(out) >= limit:
                continue
            members = [str(m) for m in g if isinstance(m, str) and m.strip()]
            # the LONGEST multi-word member that occurs as whole words is the phrase to swap
            hits = [m for m in members if (" " in m or "-" in m) and len(m) > 4 and bounded(m).search(query or "")]
            if not hits:
                continue
            hit = max(hits, key=len)
            for alt in sorted((m for m in members if m.lower() != hit.lower()), key=len, reverse=True):
                if self._symbol_alias(alt):
                    continue                   # the server already expands symbols / abbreviations
                cand = bounded(hit).sub(lambda _m, _a=alt: _a, query)
                if cand.lower() != low and cand not in out:
                    out.append(cand)
                if len(out) >= limit:
                    break
        return out[:limit]

    @staticmethod
    def _symbol_alias(alt: str) -> bool:
        """A symbol-shaped alias ("gamma_m0", "V_b", "V b", "γm0", "Vz") is not a rewording."""
        a = (alt or "").strip()
        if not a:
            return True
        if re.search(r"[_\\^{}$]|[\u0370-\u03ff]", a):
            return True
        toks = a.split()
        if all(len(t) <= 2 for t in toks):
            return True
        if len(toks) == 1 and (len(a) <= 4 or re.search(r"\d", a) or (a.isupper() and len(a) <= 6)):
            return True
        return False

    _status_cache = None

    def _corpus_status(self) -> dict:
        """What the grounding server says it is actually holding.

        Consulted only once the ladder has come back empty, and only to tell the three kinds of
        nothing apart -- rag_server answers /healthz with `spec_index` and `indexed_docs`, which is
        the one question its per-query note cannot fully answer (the note says a document is missing;
        only /healthz can name the ones that are present). RAG_API_URL points at .../query, so the
        last path segment is swapped. Cached for a minute: on an unbuilt corpus every single query
        exhausts the ladder, and the answer only changes when the user rebuilds the index."""
        try:
            if self._status_cache and (time.time() - self._status_cache[0]) < 60:
                return self._status_cache[1]
        except Exception:
            pass
        url = config.RAG_API_URL or ""
        for tail in ("/api/query", "/query"):       # longest first: "/api/query" also ends with "/query"
            if url.endswith(tail):
                url = url[: -len(tail)]
                break
        st = {}
        hdrs = {}
        if config.RAG_API_TOKEN:
            hdrs["Authorization"] = "Bearer " + config.RAG_API_TOKEN
        try:
            req = urllib.request.Request(url.rstrip("/") + "/healthz", headers=hdrs)
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.loads(r.read())
            if isinstance(d, dict):
                st = d
        except Exception:
            st = {}                                 # an older or third-party backend need not serve /healthz
        self._status_cache = (time.time(), st)
        return st

    def _not_found(self, query: str, collection: str, trail: list) -> dict:
        """The ladder is exhausted. Report WHICH of the three kinds of nothing this is.

        They are not interchangeable and the agent must not be left to guess: (i) there is no
        specification index on this machine at all, (ii) this document was never converted into the
        corpus, (iii) the corpus holds the document and the term is genuinely not in it. Only (iii)
        is a statement about the standard. Reading (i) or (ii) as (iii) is precisely the failure
        this ladder exists to stop -- a whole design run from memory while the report recorded that
        the corpus had been searched."""
        notes = " | ".join(str(t.get("note") or "") for t in trail if t.get("note"))
        low = notes.lower()
        spec = self._is_spec_collection(collection)
        tried = "; ".join(f"{t['how']} -> {t['hits']} hits" for t in trail) or "(none)"
        st = self._corpus_status() if spec else {}
        docs = [str(d) for d in (st.get("indexed_docs") or [])]
        out = {"results": [], "found": False, "collection": collection, "query": query,
               "attempts": len(trail), "escalation": trail, "attempts_made": tried}
        self.log("search_engineering_standards", f"[{collection}] ladder exhausted: {query}",
                 f"NOT FOUND after {len(trail)} attempts")
        if "no specification index" in low or (spec and st.get("spec_index") is False):
            out["not_found_kind"] = "no_specification_index"
            out["corpus_gap"] = True
            out["note"] = ("CORPUS GAP (i) -- there is NO specification index on this machine. Nothing has "
                           "been converted, so every specification query returns nothing and will keep "
                           "doing so however it is worded. This says NOTHING about whether the provision "
                           f"exists in the standard, and nothing about {collection}. Stop searching the "
                           "specifications. If you go on to design from your own knowledge of the standard, "
                           "you MUST say so in the report, in those words, and flag every value you could "
                           "not verify -- do not let the report imply the corpus was consulted.")
            return out
        m = re.match(r"\s*(\S+)\s+is not in the corpus", notes)
        if m or "is not in the corpus" in low:
            doc = m.group(1) if m else collection
            out["not_found_kind"] = "document_not_in_corpus"
            out["corpus_gap"] = True
            out["document"] = doc
            out["indexed_documents"] = docs
            out["note"] = (f"CORPUS GAP (ii) -- {doc} is not in this corpus: it was never converted, so nothing "
                           "in it can be confirmed or denied here. This is NOT evidence that the clause is "
                           "absent from the standard. The corpus does hold: "
                           + (", ".join(docs) if docs else "(the server did not say)")
                           + ". If one of those governs this check instead, query it. Otherwise name the "
                             "unavailable document in the report and flag every value you take from memory.")
            return out
        # R01 / HR-C-10: the corpus ANSWERED that the item is not tabulated (a town in neither Annex A
        # nor Annex E, ...). Pass its note through verbatim -- it names the map or table to use.
        nt = [t for t in trail if t.get("not_tabulated")]
        if nt:
            out["not_found_kind"] = "not_tabulated"
            out["not_tabulated"] = True
            out["corpus_gap"] = True
            out["note"] = str(nt[-1].get("note") or "Not tabulated in the standard (corpus reply had no note).")
            return out
        # R01: a rung that failed on the server is not a search that came back empty. If any rung
        # errored, nothing here is evidence of absence: found is None (unknown), not False.
        errs = [t for t in trail if t.get("error")]
        if errs:
            out["found"] = None
            out["not_found_kind"] = "server_error"
            out["corpus_gap"] = False
            out["server_errors"] = [str(t.get("note") or "")[:300] for t in errs]
            out["note"] = ("RETRIEVAL ERROR — not evidence of absence; retry. "
                           f"{len(errs)} of {len(trail)} attempt(s) failed on the grounding server even after one "
                           f"retry ({errs[0].get('note', '')[:160]}). Re-issue this search; if the error persists, "
                           "restart the RAG server. Do NOT report the provision as absent from the standard.")
            return out
        out["not_found_kind"] = "term_absent_from_document"
        out["note"] = (f"NOT FOUND (iii) -- {len(trail)} escalating attempts against a corpus that DOES hold "
                       f"this document all came back empty ({tried}), so the term as you phrased it is "
                       "genuinely absent from the indexed text. The filter, the exact-id lookup, the alias "
                       "rewording and the other documents have already been tried for you. Re-word ONCE using "
                       "the phrasing the specification prints, or ask for the parent section; if that misses "
                       "too, treat the provision as absent, say so in the report, and do not invent a clause "
                       "number, equation id or resistance factor to fill the gap.")
        return out

    # ---------------- RAG-to-file: keep raw chunks on disk, out of the agent's context ----------------
    _CLAUSE_RE = re.compile(r"\b[A-N]\d+(?:\.\d+)*(?:-\d+[a-z]?)?\b")   # AISC-style clause/eq codes: F2, F2.1, F2-1, H1-1, J3.6

    def _is_spec_collection(self, collection: str) -> bool:
        """RAG-to-file applies to India IS/BIS specification corpora (and legacy AISC/ASCE names).
        OpenSees/example RAGs stay inline."""
        c = (collection or "").lower()
        if "opensees" in c or "example" in c:
            return False
        try:
            from .india_collections import is_india_spec_collection
            if is_india_spec_collection(collection):
                return True
        except Exception:
            pass
        return "engineering_standard" in c or any(
            t in c for t in ("a360", "a341", "a358", "aisc", "asce",
                             "is800", "is808", "is875", "is1893", "is816", "is4000", "is1161", "is2062")
        )

    def _collection_stem(self, collection: str) -> str | None:
        """Map engineering_standards_IS* collection names to corpus stems (IS_800_2007, …)."""
        try:
            from .india_collections import stem_for_collection
            return stem_for_collection(collection)
        except Exception:
            return None

    def _render_rag(self, query: str, collection: str, out, via: str = "", sent_query: str = "") -> str:
        res = out.get("results") if isinstance(out, dict) else out
        if not isinstance(res, list):
            res = [out]
        lines = [f"# RAG query: {query}", f"# collection: {collection}  |  hits: {len(res)}"]
        if via:
            # Which rung of the escalation ladder answered. Without it the saved file silently claims
            # the first phrasing worked, which is the one thing this provenance must never imply.
            lines.append(f"# answered by: {via}"
                         + (f"  |  query as sent: {sent_query}" if sent_query and sent_query != query else ""))
        lines.append("")
        for i, h in enumerate(res, 1):
            if isinstance(h, dict):
                body = (h.get("text") or h.get("content") or h.get("chunk") or h.get("page_content")
                        or h.get("snippet") or "")
                meta = "  ".join(f"{k}={h[k]}" for k in ("score", "source", "title", "section", "page", "id")
                                 if k in h and not isinstance(h[k], (dict, list)))
                if not body:
                    body = json.dumps(h, ensure_ascii=False)
                lines.append(f"## Hit {i}  {meta}".rstrip())
                lines.append(str(body).strip())
            else:
                lines.append(f"## Hit {i}")
                lines.append(str(h).strip())
            lines.append("")
        return "\n".join(lines)

    def _clauses(self, text: str) -> list:
        seen = []
        for m in self._CLAUSE_RE.findall(text):
            if m not in seen:
                seen.append(m)
            if len(seen) >= 12:
                break
        return seen

    def _rag_file(self, d: pathlib.Path, query: str, collection: str, clause: str, qtype: str, text: str,
                  log_collection: str = "") -> pathlib.Path:
        """R03: the evidence file for one answer. Keyed on collection | clause | type | query, so the same
        words asked of two documents ("Chennai" on IS 1893 and on IS 875-3) are two files; a file that
        already exists with DIFFERENT content is never overwritten -- the new answer gets a
        content-hash suffix instead. -> the path actually written (or already holding this text)."""
        slug = re.sub(r"[^a-z0-9]+", "-", (query or "").lower()).strip("-")[:40] or "q"
        key_src = "|".join([log_collection or "", collection or "", (clause or "").strip(),
                            (qtype or "").strip().lower(), (query or "").strip()])
        key = hashlib.md5(key_src.encode("utf-8")).hexdigest()[:8]
        chash = hashlib.md5(text.encode("utf-8")).hexdigest()[:6]
        for name in (f"{slug}-{key}.txt", f"{slug}-{key}-{chash}.txt"):
            p = d / name
            if not p.exists():
                p.write_text(text, encoding="utf-8")
                return p
            try:
                if p.read_text(encoding="utf-8") == text:
                    return p                   # identical evidence already on disk
            except Exception:
                pass
        i = 2
        while True:                            # hash-suffixed name taken by other text: never overwrite
            p = d / f"{slug}-{key}-{chash}-{i}.txt"
            if not p.exists():
                p.write_text(text, encoding="utf-8")
                return p
            i += 1

    def _save_rag(self, query: str, collection: str, out, log_collection: str = "", via: str = "",
                  sent_query: str = "", clause: str = "", qtype: str = ""):
        """Spec RAG: write the full hits to rag/<slug>.txt (provenance + later re-read) and return the FULL
        result tagged with saved/query/clauses_found. The agent uses the hits inline now; once the design
        completes the run loop evicts this result to a small pointer to the saved file (agent._evict_all_rag).

        `collection` is the one that actually answered (it goes in the saved file's header, so the
        provenance names the right document); `log_collection` is the one the AGENT asked for, and is
        what goes in the activity log's leading [tag] so report._grounding_check keeps counting per
        corpus even when the hit came from a widened rung. `via` records which rung it was."""
        text = self._render_rag(query, collection, out, via=via, sent_query=sent_query)
        d = (self._job_dir() or self.jobs) / "rag"
        d.mkdir(parents=True, exist_ok=True)
        fp = self._rag_file(d, query, collection, clause, qtype, text, log_collection=log_collection)
        rel = f"rag/{fp.name}"
        res = out.get("results") if isinstance(out, dict) else out
        nhits = len(res) if isinstance(res, list) else 1
        self.log("search_engineering_standards",
                 f"[{log_collection or collection}] " + (f"{via} " if via else "") + query,
                 f"{nhits} hits -> {rel}")
        # Emit eviction metadata FIRST so saved/query/clauses_found survive even if the serialized result is later
        # truncated to a cap (agent._evict_all_rag regex-recovers them; the agent still reads the hits in between).
        tagged = {"saved": rel, "query": query, "clauses_found": self._clauses(text)}
        if isinstance(out, dict):
            for _k, _v in out.items():
                tagged.setdefault(_k, _v)
        else:
            tagged["results"] = out
        tagged["_note"] = (f"These hits are also saved to {rel}. Use them now; when this design completes they are "
                           f"replaced in your context by a pointer to {rel} -- on a later optimisation, read_file that "
                           "file if you need a clause from this search again.")
        return tagged
