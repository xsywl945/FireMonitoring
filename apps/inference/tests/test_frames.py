from fire_monitoring_inference.frames import LatestFrameQueue


def test_latest_frame_queue_drops_old_frames() -> None:
    queue: LatestFrameQueue[int] = LatestFrameQueue(capacity=2)
    queue.put(1)
    queue.put(2)
    queue.put(3)

    assert len(queue) == 2
    assert queue.get_latest() == 3
    assert len(queue) == 0
    assert queue.dropped_count == 2
