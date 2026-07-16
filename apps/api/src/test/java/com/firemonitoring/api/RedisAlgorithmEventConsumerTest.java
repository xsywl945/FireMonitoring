package com.firemonitoring.api;

import com.firemonitoring.api.events.*;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.connection.stream.*;
import org.springframework.data.redis.core.*;

import java.time.Duration;
import java.util.*;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

class RedisAlgorithmEventConsumerTest {
    @Test
    void redisOutageDoesNotEscapePollingLoop() {
        StringRedisTemplate redis = mock(StringRedisTemplate.class);
        AlgorithmEventIngestionService ingestion = mock(AlgorithmEventIngestionService.class);
        when(redis.execute(org.mockito.ArgumentMatchers.<RedisCallback<String>>any()))
                .thenThrow(new RedisConnectionFailureException("offline"));
        RedisAlgorithmEventConsumer consumer = consumer(redis, ingestion);

        assertThatCode(consumer::poll).doesNotThrowAnyException();
    }

    @Test
    @SuppressWarnings({"unchecked", "rawtypes"})
    void transientIngestionFailureRemainsUnacknowledgedAndDoesNotStopPoll() {
        StringRedisTemplate redis = mock(StringRedisTemplate.class);
        AlgorithmEventIngestionService ingestion = mock(AlgorithmEventIngestionService.class);
        StreamOperations<String, Object, Object> streams = mock(StreamOperations.class);
        MapRecord<String, Object, Object> record = mock(MapRecord.class);
        when(redis.execute(org.mockito.ArgumentMatchers.<RedisCallback<String>>any())).thenReturn("OK");
        doReturn(streams).when(redis).opsForStream();
        when(record.getId()).thenReturn(RecordId.of("1-0"));
        when(record.getValue()).thenReturn(Map.of("event", "{}"));
        when(streams.read(any(Consumer.class), any(StreamReadOptions.class), any(StreamOffset[].class)))
                .thenReturn(List.of(record), List.of());
        when(ingestion.ingest("{}")).thenThrow(new IllegalStateException("database unavailable"));
        RedisAlgorithmEventConsumer consumer = consumer(redis, ingestion);

        assertThatCode(consumer::poll).doesNotThrowAnyException();
        verify(streams, never()).acknowledge(anyString(), anyString(), any(RecordId.class));
    }

    private static RedisAlgorithmEventConsumer consumer(StringRedisTemplate redis,
                                                         AlgorithmEventIngestionService ingestion) {
        return new RedisAlgorithmEventConsumer(redis, ingestion, "monitoring.events", "spring-api",
                "spring-api-1", 20, Duration.ofMillis(10));
    }
}
