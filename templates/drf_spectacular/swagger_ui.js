"use strict";

const swaggerSettings = {{ settings|safe }};
const schemaAuthNames = {{ schema_auth_names|safe }};
let schemaAuthFailed = false;
const plugins = [];

const reloadSchemaOnAuthChange = () => {
  return {
    statePlugins: {
      auth: {
        wrapActions: {
          authorizeOauth2:(ori) => (...args) => {
            schemaAuthFailed = false;
            setTimeout(() => ui.specActions.download());
            return ori(...args);
          },
          authorize: (ori) => (...args) => {
            schemaAuthFailed = false;
            setTimeout(() => ui.specActions.download());
            return ori(...args);
          },
          logout: (ori) => (...args) => {
            schemaAuthFailed = false;
            setTimeout(() => ui.specActions.download());
            return ori(...args);
          },
        },
      },
    },
  };
};

if (schemaAuthNames.length > 0) {
  plugins.push(reloadSchemaOnAuthChange);
}

const uiInitialized = () => {
  try {
    ui;
    return true;
  } catch {
    return false;
  }
};

const isSchemaUrl = (url) => {
  if (!url) {
    return false;
  }
  try {
    const path = new URL(url, document.baseURI).pathname;
    if (path === "/api/schema/" || path.endsWith("/api/schema/")) {
      return true;
    }
  } catch {
    /* ignore */
  }
  if (!uiInitialized()) {
    return false;
  }
  return url === new URL(ui.getConfigs().url, document.baseURI).href;
};

const responseInterceptor = (response, ...args) => {
  if (!response.ok && isSchemaUrl(response.url)) {
    console.warn("schema request received '" + response.status + "'. disabling credentials for schema till logout.");
    if (!schemaAuthFailed) {
      schemaAuthFailed = true;
      setTimeout(() => ui.specActions.download());
    }
  }
  return response;
};

const injectAuthCredentials = (request) => {
  let authorized;
  if (uiInitialized()) {
    const state = ui.getState().get("auth").get("authorized");
    if (state !== undefined && Object.keys(state.toJS()).length !== 0) {
      authorized = state.toJS();
    }
  } else if (![undefined, "{}"].includes(localStorage.authorized)) {
    authorized = JSON.parse(localStorage.authorized);
  }
  if (authorized === undefined) {
    return;
  }

  // Prefer configured schema auth names, then any authorized bearer entry.
  const names = schemaAuthNames.length > 0 ? schemaAuthNames : Object.keys(authorized);
  for (const authName of [...names, ...Object.keys(authorized)]) {
    const authDef = authorized[authName];
    if (authDef === undefined) {
      continue;
    }
    const schema = authDef.schema || {};
    if (schema.type === "http" && schema.scheme === "bearer") {
      request.headers["Authorization"] = "Bearer " + authDef.value;
      return;
    }
    if (schema.type === "http" && schema.scheme === "basic") {
      request.headers["Authorization"] = "Basic " + btoa(authDef.value.username + ":" + authDef.value.password);
      return;
    }
    if (schema.type === "apiKey" && schema.in === "header") {
      request.headers[schema.name] = authDef.value;
      return;
    }
    // Authorized value without schema (our auto-auth fallback)
    if (typeof authDef.value === "string" && authDef.value.length > 0) {
      request.headers["Authorization"] = "Bearer " + authDef.value;
      return;
    }
  }
};

const requestInterceptor = (request, ...args) => {
  // Do not attach Authorize token when downloading the OpenAPI schema.
  // Tenant-user JWTs are not Django users; sending them to /api/schema/
  // used to return 401 and break Swagger ("Failed to load API definition").
  if (!isSchemaUrl(request.url)) {
    try {
      injectAuthCredentials(request);
    } catch (e) {
      console.error("auth injection failed with error: ", e);
    }
  }
  if (!["GET", undefined].includes(request.method) && request.credentials === "same-origin") {
    request.headers["{{ csrf_header_name }}"] = "{{ csrf_token }}";
  }
  return request;
};

{% if debug_swagger_auto_auth %}
async function autoAuthorizeSuperAdmin() {
  try {
    const response = await fetch("{{ swagger_dev_token_url|escapejs }}", {
      credentials: "same-origin",
    });
    if (!response.ok) {
      console.warn("Swagger auto-auth skipped:", response.status);
      return;
    }
    const data = await response.json();
    const token = data.access;
    if (!token) {
      return;
    }

    const definitions = ui.getState().getIn(["auth", "definitions"]);
    const schemeMap = definitions ? definitions.toJS() : {};
    const bearerName =
      Object.keys(schemeMap).find((name) => {
        const scheme = schemeMap[name];
        return scheme && scheme.type === "http" && scheme.scheme === "bearer";
      }) || (schemaAuthNames && schemaAuthNames[0]) || "jwtAuth";

    const scheme = schemeMap[bearerName] || {
      type: "http",
      scheme: "bearer",
      bearerFormat: "JWT",
    };

    ui.authActions.authorize({
      [bearerName]: {
        name: bearerName,
        schema: scheme,
        value: token,
      },
    });
    console.info("Swagger auto-authorized as superuser:", data.username);
  } catch (error) {
    console.warn("Swagger auto-auth failed:", error);
  }
}
{% endif %}

const ui = SwaggerUIBundle({
  url: "{{ schema_url|escapejs }}",
  dom_id: "#swagger-ui",
  presets: [SwaggerUIBundle.presets.apis],
  plugins,
  layout: "BaseLayout",
  requestInterceptor,
  responseInterceptor,
  {% if debug_swagger_auto_auth %}
  onComplete: function () {
    autoAuthorizeSuperAdmin();
  },
  {% endif %}
  ...swaggerSettings,
});

{% if oauth2_config %}ui.initOAuth({{ oauth2_config|safe }});{% endif %}
