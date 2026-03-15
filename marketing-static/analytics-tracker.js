/**
 * Customer Analytics Tracker v1.0
 * Lightweight JavaScript library for tracking customer behaviour
 * 
 * Usage:
 * <script src="/api/site/analytics-tracker.js"></script>
 * <script>
 *   AnalyticsTracker.init({
 *     apiUrl: 'https://your-api-url.com/api/customer-analytics',
 *     debug: false
 *   });
 * </script>
 */

(function(window, document) {
  'use strict';

  const AnalyticsTracker = {
    config: {
      apiUrl: '/api/customer-analytics',
      debug: false,
      trackClicks: true,
      trackScroll: true,
      trackForms: true,
      scrollDepthMarks: [25, 50, 75, 90, 100],
      sessionTimeout: 30 * 60 * 1000, // 30 minutes
    },
    
    state: {
      sessionId: null,
      visitorId: null,
      initialized: false,
      scrollDepthReached: 0,
      pageLoadTime: Date.now(),
      lastActivity: Date.now(),
    },

    /**
     * Initialize the tracker
     * @param {Object} options - Configuration options
     */
    init: function(options = {}) {
      if (this.state.initialized) {
        this.log('Tracker already initialized');
        return;
      }

      // Merge config
      this.config = { ...this.config, ...options };
      
      // Get or create visitor ID
      this.state.visitorId = this.getVisitorId();
      
      // Start session
      this.startSession();
      
      // Setup event listeners
      this.setupEventListeners();
      
      // Track initial page view
      this.trackPageView();
      
      this.state.initialized = true;
      this.log('Analytics Tracker initialized', this.config);
    },

    /**
     * Generate or retrieve visitor ID from localStorage
     */
    getVisitorId: function() {
      let visitorId = localStorage.getItem('_analytics_visitor_id');
      if (!visitorId) {
        visitorId = this.generateUUID();
        localStorage.setItem('_analytics_visitor_id', visitorId);
      }
      return visitorId;
    },

    /**
     * Get or create session ID
     */
    getSessionId: function() {
      const stored = sessionStorage.getItem('_analytics_session');
      if (stored) {
        const session = JSON.parse(stored);
        if (Date.now() - session.lastActivity < this.config.sessionTimeout) {
          session.lastActivity = Date.now();
          sessionStorage.setItem('_analytics_session', JSON.stringify(session));
          return session.id;
        }
      }
      return null;
    },

    /**
     * Start a new tracking session
     */
    startSession: async function() {
      // Check for existing valid session
      const existingSession = this.getSessionId();
      if (existingSession) {
        this.state.sessionId = existingSession;
        this.log('Resumed existing session:', existingSession);
        return;
      }

      // Get UTM parameters
      const urlParams = new URLSearchParams(window.location.search);
      
      const sessionData = {
        visitor_id: this.state.visitorId,
        landing_page: window.location.href,
        referrer: document.referrer || null,
        user_agent: navigator.userAgent,
        screen_resolution: `${screen.width}x${screen.height}`,
        language: navigator.language,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        utm_source: urlParams.get('utm_source'),
        utm_medium: urlParams.get('utm_medium'),
        utm_campaign: urlParams.get('utm_campaign'),
      };

      try {
        const response = await this.sendRequest('/track/session/start', sessionData);
        if (response && response.session_id) {
          this.state.sessionId = response.session_id;
          sessionStorage.setItem('_analytics_session', JSON.stringify({
            id: response.session_id,
            lastActivity: Date.now()
          }));
          this.log('Session started:', response.session_id);
        }
      } catch (error) {
        this.log('Failed to start session:', error);
      }
    },

    /**
     * Setup all event listeners
     */
    setupEventListeners: function() {
      // Page visibility change (for session end)
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
          this.endSession();
        }
      });

      // Before unload
      window.addEventListener('beforeunload', () => {
        this.endSession();
      });

      // Click tracking
      if (this.config.trackClicks) {
        document.addEventListener('click', (e) => this.handleClick(e), true);
      }

      // Scroll tracking
      if (this.config.trackScroll) {
        let scrollTimeout;
        window.addEventListener('scroll', () => {
          clearTimeout(scrollTimeout);
          scrollTimeout = setTimeout(() => this.handleScroll(), 100);
        }, { passive: true });
      }

      // Form tracking
      if (this.config.trackForms) {
        this.setupFormTracking();
      }

      // Track link clicks for navigation
      document.addEventListener('click', (e) => {
        const link = e.target.closest('a');
        if (link && link.href && !link.href.startsWith('javascript:')) {
          // Track as page navigation if internal link
          if (link.hostname === window.location.hostname) {
            this.trackPageView(link.href);
          }
        }
      });
    },

    /**
     * Handle click events for heatmap data
     */
    handleClick: function(e) {
      const target = e.target;
      
      const clickData = {
        page_url: window.location.href,
        element_id: target.id || null,
        element_class: target.className || null,
        element_tag: target.tagName.toLowerCase(),
        element_text: (target.textContent || '').substring(0, 50),
        x_position: e.clientX,
        y_position: e.clientY,
        viewport_width: window.innerWidth,
        viewport_height: window.innerHeight,
        session_id: this.state.sessionId,
        visitor_id: this.state.visitorId,
      };

      this.sendRequest('/track/click', clickData);
      this.log('Click tracked:', clickData);
    },

    /**
     * Handle scroll events for engagement tracking
     */
    handleScroll: function() {
      const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
      const docHeight = document.documentElement.scrollHeight - window.innerHeight;
      const scrollPercent = Math.round((scrollTop / docHeight) * 100) || 0;

      // Check if we've reached a new depth mark
      for (const mark of this.config.scrollDepthMarks) {
        if (scrollPercent >= mark && this.state.scrollDepthReached < mark) {
          this.state.scrollDepthReached = mark;
          
          const scrollData = {
            page_url: window.location.href,
            scroll_depth_percent: mark,
            max_scroll_depth: scrollPercent,
            time_on_page: Math.round((Date.now() - this.state.pageLoadTime) / 1000),
            session_id: this.state.sessionId,
            visitor_id: this.state.visitorId,
          };

          this.sendRequest('/track/scroll', scrollData);
          this.log('Scroll depth reached:', mark + '%');
        }
      }
    },

    /**
     * Setup form interaction tracking
     */
    setupFormTracking: function() {
      document.querySelectorAll('form').forEach(form => {
        this.trackForm(form);
      });

      // Watch for dynamically added forms
      const observer = new MutationObserver((mutations) => {
        mutations.forEach(mutation => {
          mutation.addedNodes.forEach(node => {
            if (node.nodeName === 'FORM') {
              this.trackForm(node);
            } else if (node.querySelectorAll) {
              node.querySelectorAll('form').forEach(form => this.trackForm(form));
            }
          });
        });
      });

      observer.observe(document.body, { childList: true, subtree: true });
    },

    /**
     * Track individual form interactions
     */
    trackForm: function(form) {
      if (form.dataset.analyticsTracked) return;
      form.dataset.analyticsTracked = 'true';

      const formId = form.id || form.name || 'unknown';
      const formName = form.getAttribute('data-form-name') || form.name || formId;
      let fieldStartTime = {};

      // Track field focus
      form.querySelectorAll('input, textarea, select').forEach(field => {
        field.addEventListener('focus', () => {
          fieldStartTime[field.name] = Date.now();
          this.sendFormEvent(formId, formName, 'focus', field.name);
        });

        field.addEventListener('blur', () => {
          const timeSpent = fieldStartTime[field.name] 
            ? Math.round((Date.now() - fieldStartTime[field.name]) / 1000)
            : 0;
          this.sendFormEvent(formId, formName, 'blur', field.name, timeSpent);
        });
      });

      // Track form submit
      form.addEventListener('submit', (e) => {
        const fields = {};
        new FormData(form).forEach((value, key) => {
          fields[key] = typeof value === 'string' ? value.substring(0, 50) : '[file]';
        });
        this.sendFormEvent(formId, formName, 'submit', null, 0, fields);
      });

      // Track form abandon (user leaves page with form started)
      window.addEventListener('beforeunload', () => {
        const hasStartedForm = Object.keys(fieldStartTime).length > 0;
        if (hasStartedForm && !form.dataset.submitted) {
          this.sendFormEvent(formId, formName, 'abandon');
        }
      });
    },

    /**
     * Send form event to API
     */
    sendFormEvent: function(formId, formName, eventType, fieldName = null, timeSpent = 0, formData = null) {
      const data = {
        page_url: window.location.href,
        form_id: formId,
        form_name: formName,
        event_type: eventType,
        field_name: fieldName,
        time_spent: timeSpent,
        session_id: this.state.sessionId,
        visitor_id: this.state.visitorId,
        form_data: formData,
      };

      this.sendRequest('/track/form', data);
      this.log('Form event:', eventType, formName, fieldName);
    },

    /**
     * Track page view
     */
    trackPageView: function(url = null) {
      const pageUrl = url || window.location.href;
      
      const pageData = {
        page_url: pageUrl,
        page_title: document.title,
        referrer: document.referrer,
        session_id: this.state.sessionId,
        visitor_id: this.state.visitorId,
        user_agent: navigator.userAgent,
        screen_resolution: `${screen.width}x${screen.height}`,
        viewport_size: `${window.innerWidth}x${window.innerHeight}`,
        language: navigator.language,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      };

      // Add UTM params if present
      const urlParams = new URLSearchParams(window.location.search);
      pageData.utm_source = urlParams.get('utm_source');
      pageData.utm_medium = urlParams.get('utm_medium');
      pageData.utm_campaign = urlParams.get('utm_campaign');
      pageData.utm_term = urlParams.get('utm_term');
      pageData.utm_content = urlParams.get('utm_content');

      this.sendRequest('/track/pageview', pageData);
      this.log('Page view tracked:', pageUrl);

      // Reset scroll tracking for new page
      this.state.scrollDepthReached = 0;
      this.state.pageLoadTime = Date.now();
    },

    /**
     * Track conversion event
     * @param {string} eventName - Name of the conversion
     * @param {string} category - Category (demo_request, signup, purchase, etc.)
     * @param {number} value - Optional monetary value
     * @param {Object} metadata - Additional data
     */
    trackConversion: function(eventName, category, value = null, metadata = {}) {
      const conversionData = {
        event_name: eventName,
        event_category: category,
        event_value: value,
        page_url: window.location.href,
        session_id: this.state.sessionId,
        visitor_id: this.state.visitorId,
        metadata: metadata,
      };

      this.sendRequest('/track/conversion', conversionData);
      this.log('Conversion tracked:', eventName, category);
    },

    /**
     * Track custom event
     * @param {string} eventName - Name of the event
     * @param {Object} eventData - Custom event data
     */
    trackEvent: function(eventName, eventData = {}) {
      const customData = {
        event_name: eventName,
        event_data: eventData,
        page_url: window.location.href,
        session_id: this.state.sessionId,
        visitor_id: this.state.visitorId,
      };

      this.sendRequest('/track/custom', customData);
      this.log('Custom event tracked:', eventName);
    },

    /**
     * End the current session
     */
    endSession: function() {
      if (!this.state.sessionId) return;

      const duration = Math.round((Date.now() - this.state.pageLoadTime) / 1000);
      
      // Use sendBeacon for reliability on page unload
      const url = `${this.config.apiUrl}/track/session/end?session_id=${this.state.sessionId}&duration_seconds=${duration}`;
      
      if (navigator.sendBeacon) {
        navigator.sendBeacon(url);
      } else {
        // Fallback to sync XHR
        const xhr = new XMLHttpRequest();
        xhr.open('POST', url, false);
        xhr.send();
      }

      this.log('Session ended, duration:', duration + 's');
    },

    /**
     * Send request to API
     */
    sendRequest: async function(endpoint, data) {
      const url = this.config.apiUrl + endpoint;
      
      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(data),
          keepalive: true,
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        return await response.json();
      } catch (error) {
        this.log('Request failed:', endpoint, error.message);
        return null;
      }
    },

    /**
     * Generate UUID v4
     */
    generateUUID: function() {
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        const r = Math.random() * 16 | 0;
        const v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
      });
    },

    /**
     * Debug logging
     */
    log: function(...args) {
      if (this.config.debug) {
        console.log('[Analytics]', ...args);
      }
    },
  };

  // Expose to global scope
  window.AnalyticsTracker = AnalyticsTracker;

  // Auto-initialize if data attribute present
  document.addEventListener('DOMContentLoaded', function() {
    const script = document.querySelector('script[data-analytics-auto-init]');
    if (script) {
      const apiUrl = script.getAttribute('data-api-url') || '/api/customer-analytics';
      const debug = script.getAttribute('data-debug') === 'true';
      AnalyticsTracker.init({ apiUrl, debug });
    }
  });

})(window, document);
