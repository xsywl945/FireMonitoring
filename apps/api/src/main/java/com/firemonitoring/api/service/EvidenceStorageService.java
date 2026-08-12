package com.firemonitoring.api.service;

import io.minio.GetObjectArgs;
import io.minio.MinioClient;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.InputStream;

@Service
public class EvidenceStorageService {
    private final MinioClient client;
    private final String bucket;
    private final int maxBytes;

    public EvidenceStorageService(
            @Value("${app.evidence.endpoint}") String endpoint,
            @Value("${app.evidence.access-key}") String accessKey,
            @Value("${app.evidence.secret-key}") String secretKey,
            @Value("${app.evidence.bucket}") String bucket,
            @Value("${app.evidence.max-bytes}") int maxBytes) {
        this.client = MinioClient.builder()
                .endpoint(endpoint)
                .credentials(accessKey, secretKey)
                .build();
        this.bucket = bucket;
        this.maxBytes = maxBytes;
    }

    public byte[] readJpeg(String objectKey) {
        if (objectKey == null || objectKey.isBlank() || !objectKey.startsWith("incidents/")) {
            throw new BadRequestException("Evidence object key is invalid");
        }
        try (InputStream input = client.getObject(
                GetObjectArgs.builder().bucket(bucket).object(objectKey).build())) {
            byte[] data = input.readNBytes(maxBytes + 1);
            if (data.length > maxBytes) {
                throw new BadRequestException("Evidence object exceeds the configured size limit");
            }
            return data;
        } catch (BadRequestException exception) {
            throw exception;
        } catch (Exception exception) {
            throw new ResourceNotFoundException("Evidence image is unavailable");
        }
    }
}
