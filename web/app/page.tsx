"use client";

import { useEffect, useState } from "react";
import { FIXED_SETTINGS, MAX_PROMPT_LENGTH, SCENE_COUNT } from "@/lib/settings";
import { SCENE_LOG_PREFIX, type Job } from "@/lib/types";

export default function Home() {
	const [topic, setTopic] = useState("");
	const [job, setJob] = useState<Job | null>(null);
	const [submitError, setSubmitError] = useState("");

	useEffect(() => {
		if (!job || job.status !== "running") return;
		const pollTimer = setInterval(async () => {
			const response = await fetch(`/api/jobs/${job.id}`);
			if (response.ok) setJob(await response.json());
		}, 2000);
		return () => clearInterval(pollTimer);
	}, [job]);

	async function submitTopic(event: React.FormEvent) {
		event.preventDefault();
		setSubmitError("");
		setJob(null);
		const response = await fetch("/api/generate", {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify({ topic }),
		});
		const generateResponseBody = await response.json();
		if (!response.ok) return setSubmitError(generateResponseBody.error);
		setJob({ id: generateResponseBody.id, topic, status: "running", log: [] });
	}

	const isRunning = job?.status === "running";
	const scenesRendered = job ? job.log.filter((line) => line.startsWith(SCENE_LOG_PREFIX)).length : 0;

	return (
		<main>
			<h1>Video Generator</h1>
			<p className="muted">Give it a topic, get back a short vertical mp4.</p>

			<form onSubmit={submitTopic}>
				<input
					value={topic}
					onChange={(event) => setTopic(event.target.value)}
					maxLength={MAX_PROMPT_LENGTH}
					placeholder="e.g. how black holes form"
					disabled={isRunning}
					autoFocus
				/>
				<button disabled={isRunning || topic.trim().length < 3}>{isRunning ? "Generating…" : "Generate"}</button>
			</form>
			{submitError && <p className="error">{submitError}</p>}

			<section className="card">
				<strong>Settings</strong> <span className="muted">(fixed in this prototype)</span>
				<dl style={{ marginTop: 8 }}>
					{FIXED_SETTINGS.map(({ label, value }) => (
						<div key={label} style={{ display: "contents" }}>
							<dt>{label}</dt>
							<dd>{value}</dd>
						</div>
					))}
				</dl>
			</section>

			{job && (
				<section className="card">
					{isRunning && (
						<>
							<p style={{ margin: 0 }}>
								{job.log.length === 0 ? "Writing script…" : `Scene ${Math.min(scenesRendered, SCENE_COUNT)} of ${SCENE_COUNT}…`}
							</p>
							<progress max={SCENE_COUNT + 1} value={scenesRendered} />
						</>
					)}
					{job.status === "error" && <p className="error">Failed: {job.error}</p>}
					{job.status === "done" && (
						<>
							<video src={`/api/video/${job.videoSlug}`} controls />
							<p>
								<a href={`/api/video/${job.videoSlug}`} download={`${job.videoSlug}.mp4`}>
									Download mp4
								</a>
							</p>
						</>
					)}
					{job.log.length > 0 && <pre className="muted">{job.log.join("\n")}</pre>}
				</section>
			)}
		</main>
	);
}
