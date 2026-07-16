package com.firemonitoring.api.events;

import org.slf4j.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.connection.stream.*;
import org.springframework.data.redis.core.*;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.*;

@Component
@ConditionalOnProperty(prefix = "app.redis.events", name = "enabled", havingValue = "true")
public class RedisAlgorithmEventConsumer {
    private static final Logger log = LoggerFactory.getLogger(RedisAlgorithmEventConsumer.class);
    private final StringRedisTemplate redis;
    private final AlgorithmEventIngestionService ingestion;
    private final String streamKey;
    private final String group;
    private final String consumerName;
    private final int batchSize;
    private final Duration blockTimeout;
    private volatile boolean groupReady;

    public RedisAlgorithmEventConsumer(StringRedisTemplate redis, AlgorithmEventIngestionService ingestion,
                                       @Value("${app.redis.events.stream-key}") String streamKey,
                                       @Value("${app.redis.events.consumer-group}") String group,
                                       @Value("${app.redis.events.consumer-name}") String consumerName,
                                       @Value("${app.redis.events.batch-size}") int batchSize,
                                       @Value("${app.redis.events.block-timeout}") Duration blockTimeout) {
        this.redis = redis;
        this.ingestion = ingestion;
        this.streamKey = streamKey;
        this.group = group;
        this.consumerName = consumerName;
        this.batchSize = batchSize;
        this.blockTimeout = blockTimeout;
    }

    @Scheduled(fixedDelayString = "${app.redis.events.poll-delay-ms:250}")
    public void poll() {
        try {
            if (!groupReady && !ensureGroup()) return;
            readAndProcess(ReadOffset.from("0-0"), false);
            readAndProcess(ReadOffset.lastConsumed(), true);
        } catch (RedisConnectionFailureException exception) {
            groupReady = false;
            log.warn("Redis event polling unavailable: {}", exception.getMessage());
        } catch (RuntimeException exception) {
            log.error("Redis event polling failed; the scheduler will retry", exception);
        }
    }

    private boolean ensureGroup() {
        try {
            redis.execute((RedisCallback<String>) connection -> connection.streamCommands().xGroupCreate(
                    streamKey.getBytes(StandardCharsets.UTF_8), group, ReadOffset.from("0-0"), true));
            groupReady = true;
            log.info("Created Redis Stream consumer group {} for {}", group, streamKey);
        } catch (RuntimeException exception) {
            if (containsBusyGroup(exception)) {
                groupReady = true;
            } else {
                log.warn("Cannot initialize Redis Stream consumer group; will retry: {}", exception.getMessage());
            }
        }
        return groupReady;
    }

    @SuppressWarnings("unchecked")
    private void readAndProcess(ReadOffset offset, boolean block) {
        StreamReadOptions options = StreamReadOptions.empty().count(batchSize);
        if (block) options = options.block(blockTimeout);
        StreamOperations<String, Object, Object> streams = redis.opsForStream();
        List<MapRecord<String, Object, Object>> records = streams.read(
                Consumer.from(group, consumerName), options, StreamOffset.create(streamKey, offset));
        if (records == null) return;
        for (MapRecord<String, Object, Object> record : records) process(record, streams);
    }

    private void process(MapRecord<String, Object, Object> record,
                         StreamOperations<String, Object, Object> streams) {
        Object value = record.getValue().get("event");
        if (value == null) {
            log.warn("Discarding Redis Stream record {} without event field", record.getId());
            acknowledge(record, streams);
            return;
        }
        try {
            IngestionResult result = ingestion.ingest(value.toString());
            acknowledge(record, streams);
            log.debug("Processed Redis Stream record {} with result {}", record.getId(), result);
        } catch (EventParseException exception) {
            log.warn("Discarding malformed algorithm event in record {}: {}", record.getId(), exception.getMessage());
            acknowledge(record, streams);
        } catch (RuntimeException exception) {
            // Do not acknowledge potentially transient database/domain failures. The same stable consumer
            // reads its pending entries from 0-0 on the next poll before accepting new records.
            log.error("Algorithm event record {} remains pending for retry", record.getId(), exception);
        }
    }

    private void acknowledge(MapRecord<String, Object, Object> record,
                             StreamOperations<String, Object, Object> streams) {
        streams.acknowledge(streamKey, group, record.getId());
    }

    private static boolean containsBusyGroup(Throwable throwable) {
        Throwable current = throwable;
        while (current != null) {
            if (current.getMessage() != null && current.getMessage().contains("BUSYGROUP")) return true;
            current = current.getCause();
        }
        return false;
    }
}
