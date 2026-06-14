package com.momopulse.collector

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import kotlinx.coroutines.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.IOException

class MomoNotificationListener : NotificationListenerService() {

    private val scope = CoroutineScope(Dispatchers.IO + Job())
    private val client = OkHttpClient()

    // REPLACE WITH YOUR ACTUAL NGROK URL (Keep the /ingest_sms at the end)
    private val API_URL = "ngrok http 80https://a1b2-c3d4-e5f6.ngrok-free.app/"
    private val USER_PHONE = "265888123456" // In production, fetch from local SharedPreferences

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val packageName = sbn.packageName
        
        // Filter: Only listen to SMS apps or WhatsApp
        if (packageName == "com.android.mms" || 
            packageName == "com.google.android.apps.messaging" || 
            packageName == "com.whatsapp") {
            
            val notificationText = extractText(sbn.notification)
            
            if (!notificationText.isNullOrEmpty()) {
                Log.d("MomoPulse", "Captured Notification: $notificationText")
                
                // Check if it looks like a MoMo transaction before sending
                if (isMomoTransaction(notificationText)) {
                    sendToBackend(notificationText)
                }
            }
        }
    }

    private fun extractText(notification: Notification): String? {
        val extras = notification.extras
        // Try to get the main text of the notification
        return extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() 
            ?: extras.getCharSequence(Notification.EXTRA_TITLE)?.toString()
    }

    private fun isMomoTransaction(text: String): Boolean {
        val lowerText = text.lowercase()
        // Simple keyword filter to avoid sending spam to your server
        return lowerText.contains("airtel") || lowerText.contains("mpamba") || 
               lowerText.contains("received") || lowerText.contains("paid") ||
               lowerText.contains("mk ")
    }

    private fun sendToBackend(smsText: String) {
        scope.launch {
            val json = JSONObject().apply {
                put("sms_text", smsText)
                put("user_phone", USER_PHONE)
            }

            val requestBody = json.toString().toRequestBody("application/json; charset=utf-8".toMediaType())
            val request = Request.Builder().url(API_URL).post(requestBody).build()

            try {
                val response = client.newCall(request).execute()
                if (response.isSuccessful) {
                    Log.i("MomoPulse", "Successfully sent to backend!")
                } else {
                    Log.e("MomoPulse", "Backend rejected data: ${response.code}")
                }
            } catch (e: IOException) {
                Log.e("MomoPulse", "Network error: ${e.message}")
            } // <--- FIXED: Removed the stray dot
        }
    }
}